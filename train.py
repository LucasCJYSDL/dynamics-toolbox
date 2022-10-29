"""
Main file to use for training dynamics models.

Author: Ian Char
"""
import os

import hydra
from hydra.utils import get_original_cwd
from omegaconf import DictConfig, OmegaConf, open_dict
from pytorch_lightning.utilities.seed import seed_everything

import dynamics_toolbox
from dynamics_toolbox.utils.lightning.constructors import\
        construct_all_pl_components_for_training


@hydra.main(config_path='./example_configs', config_name='config')
def train(cfg: DictConfig) -> None:
    """Train the model."""
    if 'model' not in cfg:
        raise ValueError('model must be specified. Choose one of the provided '
                         'model configurations and set +model=<model_config>.')
    if cfg['data_source'] == '':
        raise ValueError('data_source must be specified as either a path to an hdf5 '
                         'file or as a registered d4rl environment.')
    if 'seed' in cfg:
        seed_everything(cfg['seed'])
    # Alter config file and add defaults.
    if 'cuda_device' in cfg:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(cfg['cuda_device'])
    with open_dict(cfg):
        cfg['data_module']['data_source'] = cfg['data_source']
        if 'save_dir' not in cfg:
            cfg['save_dir'] = os.getcwd()
        elif cfg['save_dir'][0] != '/':
            cfg['save_dir'] = os.path.join(get_original_cwd(), cfg['save_dir'])
        if 'gpus' in cfg:
            cfg['gpus'] = str(cfg['gpus'])
    model, data, trainer, logger, cfg = construct_all_pl_components_for_training(cfg)
    print(OmegaConf.to_yaml(cfg))
    if cfg['logger'] == 'mlflow':
        save_path = os.path.join(cfg['save_dir'], logger.experiment_id, logger.run_id)
    else:
        save_path = os.getcwd()
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    OmegaConf.save(cfg, os.path.join(save_path, 'config.yaml'))
    logger.log_hyperparams(dict(cfg['model'], **cfg['data_module']))
    trainer.fit(model, data)
    if data.test_dataloader() is not None:
        test_dict = trainer.test(model, datamodule=data)[0]
        tune_metric = cfg.get('tune_metric', 'test/loss')
        return_val = test_dict[tune_metric]
        if cfg.get('tune_objective', 'minimize') == 'maximize':
            return_val *= -1
        return return_val
    else:
        return 0


if __name__ == '__main__':
    train()

