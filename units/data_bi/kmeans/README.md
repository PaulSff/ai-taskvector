# KMeans

K-means clustering (sklearn `KMeans`). Fit on first run; assigns each row to a cluster. Adds `_cluster` column.

## Purpose

Clusters numeric rows into k groups. No target column; uses all numeric columns as features. Model stored in state. Params: `n_clusters` (default 3).

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — numeric features      |
|              | in        | int    | `n_clusters` — number of clusters |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` + `_cluster`           |
|              | out       | list   | `predictions` — cluster ids    |
| **Params**   | config    | —      | `n_clusters`                   |

## Example

**Input:** table with numeric columns, `n_clusters`: 3  
**Output:** table with `_cluster` (0, 1, or 2); `predictions` list on output port.
