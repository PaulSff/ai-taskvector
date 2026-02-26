"""Data/BI units: one folder per unit with README (Pandas + Scikit-Learn)."""

from units.data_bi.source import register_data_source
from units.data_bi.filter import register_filter
from units.data_bi.topk import register_topk
from units.data_bi.read_table import register_read_table
from units.data_bi.filter_rows import register_filter_rows
from units.data_bi.sort_values import register_sort_values
from units.data_bi.head import register_head
from units.data_bi.tail import register_tail
from units.data_bi.select_columns import register_select_columns
from units.data_bi.dropna import register_dropna
from units.data_bi.fillna import register_fillna
from units.data_bi.groupby_agg import register_groupby_agg
from units.data_bi.merge_tables import register_merge_tables
from units.data_bi.value_counts import register_value_counts
from units.data_bi.describe import register_describe
from units.data_bi.train_test_split import register_train_test_split
from units.data_bi.standard_scaler import register_standard_scaler
from units.data_bi.minmax_scaler import register_minmax_scaler
from units.data_bi.one_hot_encoder import register_one_hot_encoder
from units.data_bi.pca import register_pca
from units.data_bi.logistic_regression import register_logistic_regression
from units.data_bi.random_forest_classifier import register_random_forest_classifier
from units.data_bi.linear_regression import register_linear_regression
from units.data_bi.random_forest_regressor import register_random_forest_regressor
from units.data_bi.kmeans import register_kmeans
from units.data_bi.metrics import register_metrics


def register_data_bi_units() -> None:
    """Register all data_bi units (legacy + pandas + sklearn)."""
    register_data_source()
    register_filter()
    register_topk()
    register_read_table()
    register_filter_rows()
    register_sort_values()
    register_head()
    register_tail()
    register_select_columns()
    register_dropna()
    register_fillna()
    register_groupby_agg()
    register_merge_tables()
    register_value_counts()
    register_describe()
    register_train_test_split()
    register_standard_scaler()
    register_minmax_scaler()
    register_one_hot_encoder()
    register_pca()
    register_logistic_regression()
    register_random_forest_classifier()
    register_linear_regression()
    register_random_forest_regressor()
    register_kmeans()
    register_metrics()


__all__ = ["register_data_bi_units"]
