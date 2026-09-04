"""
src/track_experiments.py

Retrofits MLflow tracking onto the model comparisons already done manually
in notebooks/03_route607_modeling.ipynb. Retrains each model fresh (not
loaded from notebook state) so this script is a standalone, reproducible
record of the experiment history -- run it, then `mlflow ui` to browse
params/metrics/artifacts for every run instead of scrolling notebook output.
"""
import pandas as pd
import mlflow
import mlflow.sklearn
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score, precision_score, recall_score, mean_absolute_error

PROCESSED_DIR = "data/processed"

TEST_DATES = [
    "2024-01-16", "2021-12-07", "2026-02-14", "2022-12-15", "2021-02-10",
    "2023-12-12", "2024-02-20", "2025-01-31", "2025-03-23", "2026-02-27",
    "2025-03-29",
]

mlflow.set_experiment("route607-delay-prediction")


def load_split():
    final = pd.read_parquet(f"{PROCESSED_DIR}/modeling_table_route607.parquet")
    final_clean = final.dropna(subset=["is_delayed"]).copy()

    precip_median = final_clean[~final_clean["service_date"].isin(TEST_DATES)]["precip_mm"].median()
    final_clean["precip_missing"] = final_clean["precip_mm"].isna().astype(int)
    final_clean["precip_mm"] = final_clean["precip_mm"].fillna(precip_median)
    final_clean["stop_id"] = final_clean["stop_id"].astype(str)

    train = final_clean[~final_clean["service_date"].isin(TEST_DATES)]
    test = final_clean[final_clean["service_date"].isin(TEST_DATES)]
    return train, test, precip_median


def log_classifier_run(run_name, model, categorical, numeric, train, test, notes):
    with mlflow.start_run(run_name=run_name):
        mlflow.log_param("model_type", type(model.named_steps["clf"] if hasattr(model, "named_steps") else model).__name__)
        mlflow.log_param("categorical_features", categorical)
        mlflow.log_param("numeric_features", numeric)
        mlflow.log_param("class_weight", "balanced")
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))
        mlflow.set_tag("notes", notes)

        X_train, y_train = train[categorical + numeric], train["is_delayed"]
        X_test, y_test = test[categorical + numeric], test["is_delayed"]
        model.fit(X_train, y_train)

        preds = model.predict(X_test)
        proba = model.predict_proba(X_test)[:, 1]

        auc = roc_auc_score(y_test, proba)
        precision = precision_score(y_test, preds)
        recall = recall_score(y_test, preds)

        mlflow.log_metric("roc_auc", auc)
        mlflow.log_metric("precision_delayed", precision)
        mlflow.log_metric("recall_delayed", recall)
        mlflow.sklearn.log_model(
            model, name="model",
            skops_trusted_types=["functools.partial", "sklearn.utils.validation.check_array"],
            )

        print(f"{run_name}: ROC-AUC={auc:.4f}, precision={precision:.3f}, recall={recall:.3f}")
        return auc


if __name__ == "__main__":
    train, test, precip_median = load_split()

    for df in [train, test]:
        df["weekday"] = df["weekday"].astype(str)

    # --- Run 1: logistic regression, no stop_id (Step 4.3) ---
    categorical = ["weekday"]
    numeric = ["hour", "temperature_c", "precip_mm", "precip_missing", "is_rush_hour", "is_snow_proxy", "is_rain_proxy"]
    preprocess = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("num", StandardScaler(), numeric),
    ])
    lr_model = Pipeline([("prep", preprocess), ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))])
    log_classifier_run(
        "logistic_regression_baseline", lr_model, categorical, numeric, train, test,
        "First real model, Step 4.3. No stop_id -- weekday and weather only."
    )

    # --- Run 2: gradient boosting, no stop_id (Step 4.4) ---
    categorical_gbm = ["weekday"]
    train_gbm = train.copy()
    test_gbm = test.copy()
    train_gbm["weekday"] = train_gbm["weekday"].astype("category")
    test_gbm["weekday"] = pd.Categorical(test_gbm["weekday"], categories=train_gbm["weekday"].cat.categories)

    gbm_baseline = HistGradientBoostingClassifier(categorical_features=categorical_gbm, class_weight="balanced", random_state=42)
    log_classifier_run(
        "gradient_boosting_baseline", gbm_baseline, categorical_gbm, numeric, train_gbm, test_gbm,
        "Step 4.4. Same features as logistic regression baseline -- near-tie result, ROC-AUC ~0.605 for both."
    )

    # --- Run 3: gradient boosting + stop_id (Step 4.6, the final shipped model) ---
    categorical_final = ["weekday", "stop_id"]
    train_final = train.copy()
    test_final = test.copy()
    train_final["weekday"] = train_final["weekday"].astype("category")
    train_final["stop_id"] = train_final["stop_id"].astype("category")
    test_final["weekday"] = pd.Categorical(test_final["weekday"], categories=train_final["weekday"].cat.categories)
    test_final["stop_id"] = pd.Categorical(test_final["stop_id"], categories=train_final["stop_id"].cat.categories)

    gbm_final = HistGradientBoostingClassifier(categorical_features=categorical_final, class_weight="balanced", random_state=42)
    log_classifier_run(
        "gradient_boosting_with_stop_id", gbm_final, categorical_final, numeric, train_final, test_final,
        "Step 4.6, FINAL SHIPPED MODEL. Adding stop_id raised ROC-AUC from ~0.605 to ~0.705 -- "
        "prompted by finding a 16x delay-rate spread across the route's 52 stops."
    )

    # --- Run 4: delay-severity regression (Step 4.8, negative result -- logged anyway) ---
    with mlflow.start_run(run_name="delay_severity_regression_NOT_SHIPPED"):
        cat_features = ["weekday", "stop_id"]
        all_features = cat_features + numeric

        train_delayed = train_final[train_final["is_delayed"] == 1]
        test_delayed = test_final[test_final["is_delayed"] == 1]

        X_train_reg = train_delayed[all_features]
        y_train_reg = train_delayed["delay_minutes"]
        X_test_reg = test_delayed[all_features]
        y_test_reg = test_delayed["delay_minutes"]

        reg = HistGradientBoostingRegressor(categorical_features=cat_features, random_state=42)
        reg.fit(X_train_reg, y_train_reg)
        preds_reg = reg.predict(X_test_reg)

        mae = mean_absolute_error(y_test_reg, preds_reg)
        baseline_mae = mean_absolute_error(y_test_reg, [y_train_reg.mean()] * len(y_test_reg))

        mlflow.log_param("model_type", "HistGradientBoostingRegressor")
        mlflow.log_param("target", "delay_minutes, delayed trips only")
        mlflow.log_metric("mae_minutes", mae)
        mlflow.log_metric("baseline_mae_minutes", baseline_mae)
        mlflow.set_tag("notes",
            "Step 4.8. NOT SHIPPED -- model MAE (1.82) does not beat naive mean baseline (1.79). "
            "Genuine negative finding: severity of delay, once it occurs, is weakly predictable "
            "and not well explained by available features.")

        print(f"delay_severity_regression: MAE={mae:.2f} vs baseline={baseline_mae:.2f} -- NOT SHIPPED")

    print("\nAll runs logged. View with: mlflow ui")