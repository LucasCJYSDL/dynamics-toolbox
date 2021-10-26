"""
Construction functions for lightning.

Author: Ian Char
"""
from typing import Tuple
import os

import numpy as np
from omegaconf import DictConfig, open_dict
import pytorch_lightning as pl
from pytorch_lightning import LightningDataModule
from pytorch_lightning.loggers.base import LightningLoggerBase
from pytorch_lightning.loggers.tensorboard import TensorBoardLogger
import torch

from dynamics_toolbox.models import pl_models
from dynamics_toolbox.data import pl_data_modules
from dynamics_toolbox.models.pl_models.abstract_pl_model import AbstractPlModel
from dynamics_toolbox.utils.lightning.single_progress_bar import SingleProgressBar
from dynamics_toolbox.utils.pytorch.modules.normalizer import Normalizer


def construct_all_pl_components_for_training(
        cfg: DictConfig
) -> Tuple[AbstractPlModel, LightningDataModule, pl.Trainer, LightningLoggerBase, DictConfig]:
    """Construct all components needed for training.

    Args:
        cfg: The configuration containing trainer, model, data_module info.

    Returns:
        * The data module.
        * The model to be used for training.
        * Trainer to be used for training.
        * The altered configuration.
    """
    data = getattr(pl_data_modules, cfg['data_module']['data_module_type'])(
            **cfg['data_module'])
    with open_dict(cfg):
        cfg['model']['input_dim'] = data.input_dim
        cfg['model']['output_dim'] = data.output_dim
        if 'member_config' in cfg['model']:
            cfg['model']['member_config']['input_dim'] = data.input_dim
            cfg['model']['member_config']['output_dim'] = data.output_dim
    if 'normalization' not in cfg:
        normalizer = None
    elif cfg['normalization'] == 'standardize':
        normalizer = Normalizer(
                torch.Tensor(np.mean(data.input_data, axis=0)),
                torch.Tensor(np.std(data.input_data, axis=0)),
                torch.Tensor(np.mean(data.output_data, axis=0)),
                torch.Tensor(np.std(data.output_data, axis=0)),
        )
    else:
        raise ValueError(f'Normalization scheme {cfg["normalization"]} not found.')
    model = construct_pl_model(cfg['model'], normalizer=normalizer)
    callbacks = []
    if 'early_stopping' in cfg:
        callbacks.append(get_early_stopping_for_val_loss(cfg['early_stopping']))
    max_epochs = (1000 if 'max_epochs' not in cfg['trainer']
                  else cfg['trainer']['max_epochs'])
    callbacks.append(SingleProgressBar(max_epochs))
    if cfg['logger'] == 'mlflow':
        from pytorch_lightning.loggers.mlflow import MLFlowLogger
        logger = MLFlowLogger(
            experiment_name=cfg['experiment_name'],
            tracking_uri=cfg.get('tracking_uri', None),
            save_dir=cfg['save_dir'],
            run_name=cfg.get('run_name', None),
        )
    else:
        if 'run_name' in cfg:
            name = os.path.join(cfg['experiment_name'], cfg['run_name'])
        else:
            name = cfg['experiment_name']
        logger = TensorBoardLogger(
            save_dir=cfg['save_dir'],
            name=name,
        )
    trainer = pl.Trainer(
        **cfg['trainer'],
        logger=logger,
        callbacks=callbacks,
        progress_bar_refresh_rate=0,
    )
    return model, data, trainer, logger, cfg


def construct_pl_model(cfg: DictConfig, **kwargs) -> AbstractPlModel:
    """Construct a pytorch lightning model.

    Args:
        cfg: The configuration to create. Must have the following
            - model_type: the model type as registered in
              dynamics_toolbox/models/__init__.py

    Returns:
        The pytorch lightning model.
    """
    if 'model_type' not in cfg:
        raise ValueError('Configuration does not have model_type')
    return getattr(pl_models, cfg['model_type'])(**cfg, **kwargs)


def get_early_stopping_for_val_loss(cfg: DictConfig) -> pl.callbacks.EarlyStopping:
    """Get an early stopping callback with a certain patience.

    Args:
        cfg: The configuration for early stopping.

    Returns:
        The early stopping callback to use in the trainer.
    """
    return pl.callbacks.EarlyStopping(
        monitor='val/loss',
        min_delta=cfg['min_delta'],
        patience=cfg['patience'],
        mode='min',
    )
