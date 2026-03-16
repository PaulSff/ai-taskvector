# Data / BI Environment (Unit-based Data Workflows)

Custom RL environment for training and fine-tuning agents on **data-manipulation and smart filtering / BI-style tasks**: classification, tabular regression, time-series forecasting, anomaly detection, ranking, and selection. The main differentiator is the **unit-based workflow**: each tool (filter, sort, model, ranker) is a **unit** in the process graph, orchestrated by the RL assistant (RL Coach).

## Example use case

- **Input**: `flight-offers.json` (or any tabular/JSON dataset).
- **Goal**: Produce a **top-10** selection that maximizes downstream success (e.g. deal closed 1/0 from real sales data).
- **Feedback**: User metadata + real outcome labels (deal occurred or not).
- **Units**: DataSource → optional Filter/Sort/Featurizer → Ranker/TopK → output; optionally a Classifier/Regressor unit for predicting deal probability, with reward from actual outcomes.

The RL agent learns which filters, sorts, and model choices to apply (and with what parameters) to maximize reward (e.g. deal rate on the chosen top-K).

---

## PriorLabs / TabPFN (foundation reference)

[PriorLabs](https://github.com/PriorLabs) provides open-source, **non-commercial** building blocks that fit this environment:

| Project | Role |
|--------|------|
| **TabPFN** | Foundation model for tabular data: classification and regression with sklearn-compatible API (`TabPFNClassifier`, `TabPFNRegressor`). Good for small-to-medium tables (e.g. &lt;50k rows with TabPFN-2.5). |
| **tabpfn-time-series** | Zero-shot time-series forecasting (NeurIPS 2024 TRL/TSALM). |
| **tabpfn-extensions** | Interpretability (SHAP, feature selection), unsupervised (outlier/anomaly detection, imputation, data generation), many-class, HPO, post-hoc ensembles. |

**Licensing**: TabPFN-2.5 weights are non-commercial; code and TabPFN v2 are Apache 2.0 with attribution. For production/commercial use, PriorLabs offers an Enterprise Edition.

**Use in this env**: TabPFN (and sklearn) can back **Classifier**, **Regressor**, and **AnomalyDetector** units. The RL agent chooses which unit to invoke and with what hyperparameters; reward comes from downstream metrics (accuracy, deal rate, etc.).

---

## Stack: Scikit-Learn, Pandas, RAG

| Layer | Recommendation | Role |
|-------|----------------|--------|
| **Learning pipelines** | **Scikit-Learn** (and optionally TabPFN) | Classification, regression, preprocessing. TabPFN is sklearn-compatible; we can wrap both in a single “Model” unit type or separate Classifier/Regressor/Anomaly units. |
| **Data ingestion / cleaning / tables** | **Pandas** (primary) or **list-of-dicts** (minimal) | Load JSON/CSV, clean, join, aggregate. Our executor can pass tables as `list[dict]` or `pd.DataFrame` between units. Pandas is the natural choice for real BI/analytics. |
| **Semantic context** | **Current RAG** (optional) | Search over docs, schemas, and workflow catalogue. Use RAG to inform the RL Coach which columns/sources/filters are relevant (e.g. “flight-offers schema”), not as the primary data path. |

**Summary**: Use **Pandas** (or your existing RAG-backed metadata) for loading and cleaning; use **Scikit-Learn** (and TabPFN where useful) for model units; use **RAG** for semantic guidance and schema/docs, not as the main data pipeline.

---

## Unit types (Pandas + Scikit-Learn)

All units use **pandas** (DataFrame) and **scikit-learn** where applicable. Tables are passed as list-of-dicts at graph boundaries; internally converted to DataFrame.

### Pandas units

| Unit | Purpose | Main inputs / params |
|------|---------|----------------------|
| **DataSource** | Table from state (reset) or params path (JSON/CSV). | — ; or `path`, `format` |
| **ReadTable** | Load from file (csv, json, jsonl, parquet). | `path`, `format` |
| **Filter** / **FilterRows** | Filter rows by column + op + value or by `query`. | `table`, `value` (action), `column`, `op` or `query` |
| **SortValues** | Sort by column(s). | `table`, `by`, `ascending` |
| **Head** | First n rows. | `table`, `n` |
| **Tail** | Last n rows. | `table`, `n` |
| **TopK** | First k rows (alias for head). | `table`, `k` |
| **SelectColumns** | Keep only listed columns. | `table`, `columns` |
| **DropNa** | Drop rows with missing values. | `table`, optional `subset` |
| **FillNa** | Fill missing with value. | `table`, `value` |
| **GroupByAgg** | Group by column(s) and aggregate (e.g. mean, size). | `table`, `by`, `agg` |
| **MergeTables** | Join two tables. | `left`, `right`, `on`, `how` |
| **ValueCounts** | Count values in a column. | `table`, `column` |
| **Describe** | Numeric summary stats. | `table` |

### Scikit-Learn units

| Unit | Purpose | Main inputs / params |
|------|---------|----------------------|
| **TrainTestSplit** | Split table into train/test. | `table`, `test_size`, `random_state` |
| **StandardScaler** | Fit/transform numeric columns (z-score). | `table` |
| **MinMaxScaler** | Fit/transform numeric columns (0–1). | `table` |
| **OneHotEncoder** | One-hot encode categorical columns. | `table`, optional `columns` |
| **PCA** | Dimensionality reduction. | `table`, `n_components` |
| **LogisticRegression** | Fit/predict classification. | `table`, `target_column` |
| **RandomForestClassifier** | Fit/predict classification. | `table`, `target_column` |
| **LinearRegression** | Fit/predict regression. | `table`, `target_column` |
| **RandomForestRegressor** | Fit/predict regression. | `table`, `target_column` |
| **KMeans** | Clustering; adds `_cluster` column. | `table`, `n_clusters` |
| **Metrics** | Accuracy, F1, MSE, R² from `y_true` / `y_pred` columns. | `table`, `y_true`, `y_pred` |

Observation space: summary of current table(s), user metadata, optional RAG context.  
Action space: discrete/continuous choices for which unit to trigger and parameters (e.g. filter column, threshold, `k` for TopK).  
Reward: from downstream outcome (e.g. deal rate on selected top-10, or accuracy/F1 on held-out labels).

---

## Integration with this repo

- **EnvSpec**: `DataBIEnvSpec` in `environments/native/data_bi/spec.py` — `register_units()`, `build_initial_state()`, `check_done()`, `extend_info()`, `get_goal_override()`.
- **Loader**: `load_data_bi_env()` in `loader.py`; config keys: `process_graph_path`, `goal`, `rewards`, plus optional `data_path`, `user_metadata_path`.
- **Process graph**: `environment_type: data_bi`; units: DataSource, Filter, Sort, TopK, RLAgent, (optional) Classifier/Regressor/AnomalyDetector.
- **GoalConfig**: Extended with `target_metric` (e.g. `deal_rate`, `accuracy`), `target_value`, `feedback_column` (e.g. `deal` 0/1).

**Optional dependencies** (for full pipelines): `pandas`, `scikit-learn`, `tabpfn` (and `tabpfn-extensions` for anomaly detection). Core env runs with list-of-dicts only.

---

## Data visualization

Neither **pandas** nor **scikit-learn** ship a dashboard app. They provide programmatic plotting that you can use before/during training:

| Source | What it provides |
|--------|------------------|
| **Pandas** | `df.plot()` — line, bar, hist, scatter, box, etc. (matplotlib backend). `df.hist()`, `df.plot.scatter()`. No UI; you call these in code or notebooks. |
| **Scikit-learn** | Display utilities (matplotlib): `ConfusionMatrixDisplay`, `RocCurveDisplay`, `PartialDependenceDisplay`, `DecisionBoundaryDisplay`. Use in scripts or notebooks. |

**In this repo:**

- **matplotlib** is already in `requirements.txt`. The data_bi spec supports `render_mode="human"`: each step can print a short summary and, if pandas is available, show a small plot (e.g. numeric columns histogram or current table head).
- **Optional**: use **seaborn** (`pip install seaborn`) for nicer statistical plots (distributions, heatmaps, pair plots). You can add a small **Streamlit** or **Flet** page (the project uses Flet for the main GUI) that loads a table and displays `st.dataframe(df)` plus charts via pandas/matplotlib or seaborn.
- For a **standalone dashboard**, run the provided script (see below) to explore a table and plot numeric columns before wiring the env.

**In-env:** with `render_mode="human"`, `env.render()` prints a one-line summary (step, row_count, target_metric). Set `env.render_plot = True` to also show histograms of numeric columns from the current pipeline output (matplotlib).

**Standalone viewer:** to inspect a table file before training, run:

```bash
python -m environments.native.data_bi.data_viewer path/to/flight-offers.json
python -m environments.native.data_bi.data_viewer data.csv --format csv --hist
```

This prints shape, columns, and a table head; use `--hist` to plot histograms of numeric columns (requires matplotlib).

---

## Example process graph and training

See `config/examples/data_bi_workflow.yaml` for a minimal graph: DataSource → Filter (value from RLAgent) → TopK. Train with:

```yaml
# training config
environment:
  source: native
  type: data_bi
  process_graph_path: config/examples/data_bi_workflow.yaml
goal:
  target_metric: deal_rate
  feedback_column: deal
```

Provide table data via `reset(options={"table": [...]})` or `data_path` to a JSON file (list of objects or `{"offers": [...]}` / `{"data": [...]}`).
