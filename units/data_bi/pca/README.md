# PCA

Principal component analysis: reduce numeric columns to fewer components (sklearn `PCA`). Fit on first run.

## Purpose

Projects numeric features onto the first n principal components. Drops original numeric columns and adds PC1, PC2, ... Useful for dimensionality reduction and visualization.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — input                |
|              | in        | int    | `n_components` — number of PCs |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — non-numeric cols + PC1, PC2, ... |
| **Params**   | config    | —      | `n_components` (default 2)    |

## Example

**Input:** table with 10 numeric columns, `n_components`: 2  
**Output:** table with 2 columns PC1, PC2 (and any non-numeric columns kept).
