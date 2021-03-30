import scanpy as sc
import scvi.dataset
import anndata
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def process_dataset(adata: anndata.AnnData, args):
    if args.subset_genes:
        sc.pp.highly_variable_genes(adata, n_top_genes=args.subset_genes, flavor='seurat_v3')
        adata = adata[:, adata.var.highly_variable]
    if args.norm_cell_read_counts:
        sc.pp.normalize_total(adata, target_sum=1e4)
    if args.quantile_norm:
        from sklearn.preprocessing import quantile_transform
        adata.X = quantile_transform(adata.X, axis=1, copy=True)
    if args.log1p:
        sc.pp.log1p(adata)

    if 'batch_indices' in adata.obs:
        batches = sorted(list(adata.obs.batch_indices.unique()))
        if isinstance(batches[-1], str) or batches[0] != 0 or batches[-1] + 1 != len(batches):
            logger.info('Converting batch names to integers...')
            adata.obs['batch_indices'] = adata.obs.batch_indices.apply(lambda x: batches.index(x))
        adata.obs.batch_indices = adata.obs.batch_indices.astype(str).astype('category')

    adata.obs_names_make_unique()

    if hasattr(args, 'pathway_csv_path') and args.pathway_csv_path:
        mat = pd.read_csv(args.pathway_csv_path, index_col=0)
        if args.trainable_gene_emb_dim == 0:
            genes = sorted(list(set(mat.index).intersection(adata.var_names)))
            logger.info(f'Using {mat.shape[1]}-dim fixed gene embedding for {len(genes)} genes appeared in both the gene-pathway matrix and the dataset.')
            adata = adata[:, genes]
            adata.varm['gene_emb'] = mat.loc[genes, :].values
        else:
            logger.info(f'{mat.shape[1]} dimensions of the gene embeddings will be trainable. Keeping all genes in the dataset') 
            mat = mat.reindex(index = adata.var_names, fill_value=0.0)
            adata.varm['gene_emb'] = mat.values
    # if hasattr(args, 'color_by') and (hasattr(args, 'no_draw') and not args.no_draw) and (hasattr(args, 'no_eval') and not args.no_eval):
    #     for col_name in args.color_by:
    #         assert col_name in adata.obs, f"{col_name} in args.color_by but not in adata.obs"
    if hasattr(args, 'max-supervised-weight') and args.max_supervised_weight:
        assert 'cell_types' in adata.obs, f"For supervised learning, the 'cell_types' column must be present in the adata.obs object."

    logger.info(f'adata: {adata}')
    if 'batch_indices' in adata.obs:
        logger.info(f'n_batches: {adata.obs.batch_indices.nunique()}')
    if not args.no_eval and 'cell_types' in adata.obs:
        logger.info(f'n_labels: {adata.obs.cell_types.nunique()}')
        logger.info(f'label counts:\n{adata.obs.cell_types.value_counts()}')
    return adata


def train_test_split(adata : anndata.AnnData, test_ratio=0.1, seed=1):
    rng = np.random.default_rng(seed=seed)
    test_indices = rng.choice(adata.n_obs, size=int(test_ratio * adata.n_obs), replace=False)
    train_indices = list(set(range(adata.n_obs)).difference(test_indices))
    train_adata = adata[adata.obs_names[train_indices], :]
    test_adata = adata[adata.obs_names[test_indices], :]
    logger.info(f'Keeping {test_adata.n_obs} cells ({test_ratio:g}) as test data.')
    return train_adata, test_adata


class DatasetConfig:
    def __init__(self, name, get_dataset):
        self.name = name
        self.get_dataset = lambda args: process_dataset(get_dataset(args), args)


cortex_config = DatasetConfig("cortex", lambda args: scvi.dataset.CortexDataset('../data/cortex').to_anndata())
hemato_config = DatasetConfig("hemato", lambda args: scvi.dataset.CortexDataset('../data/hemato').to_anndata())
prefrontal_cortex_config = DatasetConfig("prefrontalCortex", lambda args: scvi.dataset.PreFrontalCortexStarmapDataset('../data/PreFrontalCortex').to_anndata())

available_datasets = dict(cortex=cortex_config, prefrontalCortex=prefrontal_cortex_config)
