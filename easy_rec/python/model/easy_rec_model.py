# -*- encoding: utf-8 -*-
# Copyright (c) Alibaba, Inc. and its affiliates.

import logging
import re
from abc import abstractmethod

import six
import tensorflow as tf

from easy_rec.python.compat import regularizers
from easy_rec.python.layers import embed_input_layer
from easy_rec.python.layers import input_layer
from easy_rec.python.utils import estimator_utils
from easy_rec.python.utils import restore_filter
from easy_rec.python.utils.load_class import get_register_class_meta

if tf.__version__ >= '2.0':
  tf = tf.compat.v1

_EASY_REC_MODEL_CLASS_MAP = {}
_meta_type = get_register_class_meta(
    _EASY_REC_MODEL_CLASS_MAP, have_abstract_class=True)


class EasyRecModel(six.with_metaclass(_meta_type, object)):

  def __init__(self,
               model_config,
               feature_configs,
               features,
               labels=None,
               is_training=False):
    self._base_model_config = model_config
    self._model_config = model_config
    self._is_training = is_training
    self._feature_dict = features

    self._feature_configs = feature_configs

    self.build_input_layer(model_config, feature_configs)

    self._emb_reg = regularizers.l2_regularizer(self.embedding_regularization)

    self._labels = labels
    self._prediction_dict = {}
    self._loss_dict = {}

  @property
  def embedding_regularization(self):
    return self._base_model_config.embedding_regularization

  def build_input_layer(self, model_config, feature_configs):
    if feature_configs is not None:
      self._input_layer = input_layer.InputLayer(
          feature_configs,
          model_config.feature_groups,
          use_embedding_variable=model_config.use_embedding_variable)
    else:
      self._input_layer = embed_input_layer.EmbedInputLayer(
          model_config.feature_groups)

  @abstractmethod
  def build_predict_graph(self):
    pass

  @abstractmethod
  def build_loss_graph(self):
    pass

  @abstractmethod
  def build_metric_graph(self, eval_config):
    pass

  @abstractmethod
  def get_outputs(self):
    pass

  def restore(self,
              ckpt_path,
              include_global_step=False,
              ckpt_var_map_path='',
              force_restore_shape_compatible=False):
    """Restore variables from ckpt_path.

    steps:
      1. list the variables in graph that need to be restored
      2. inspect checkpoint and find the variables that could restore from checkpoint
         substitute scope names in case necessary
      3. call tf.train.init_from_checkpoint to restore the variables

    Args:
       ckpt_path: checkpoint path to restore from
       include_global_step: whether to restore global_step variable
       ckpt_var_map_path: variable map from graph variables to variables in a checkpoint
          each line consists of: variable name in graph  variable name in ckpt
       force_restore_shape_compatible: if variable shape is incompatible, clip or pad
          variables in checkpoint, and then restore

    Returns:
      IncompatibleShapeRestoreHook if force_shape_compatible else None
    """
    name2var_map = self._get_restore_vars(ckpt_var_map_path)
    logging.info('start to restore from %s' % ckpt_path)

    if tf.gfile.IsDirectory(ckpt_path):
      ckpt_path = tf.train.latest_checkpoint(ckpt_path)
      print('ckpt_path is model_dir,  will use the latest checkpoint: %s' %
            ckpt_path)

    ckpt_reader = tf.train.NewCheckpointReader(ckpt_path)
    ckpt_var2shape_map = ckpt_reader.get_variable_to_shape_map()
    if not include_global_step:
      ckpt_var2shape_map.pop(tf.GraphKeys.GLOBAL_STEP, None)

    vars_in_ckpt = {}
    incompatible_shape_var_map = {}
    fail_restore_vars = []
    for variable_name, variable in sorted(name2var_map.items()):
      if variable_name in ckpt_var2shape_map:
        print('restore %s' % variable_name)
        ckpt_var_shape = ckpt_var2shape_map[variable_name]
        var_shape = variable.shape.as_list()
        if ckpt_var_shape == var_shape:
          vars_in_ckpt[variable_name] = variable
        elif len(ckpt_var_shape) == len(var_shape):
          if force_restore_shape_compatible:
            # create a variable compatible with checkpoint to restore
            with tf.variable_scope(''):
              tmp_var = tf.get_variable(
                  name=variable_name + '_T_E_M_P',
                  shape=ckpt_var_shape,
                  dtype=variable.dtype)
            vars_in_ckpt[variable_name] = tmp_var
            incompatible_shape_var_map[variable] = tmp_var
          else:
            logging.warning(
                'Variable [%s] is available in checkpoint, but '
                'incompatible shape with model variable.', variable_name)
        else:
          logging.warning(
              'Variable [%s] is available in checkpoint, but '
              'incompatible shape dims with model variable.', variable_name)
      else:
        fail_restore_vars.append(variable_name)
    for variable_name in fail_restore_vars:
      if 'Momentum' not in variable_name:
        logging.warning('Variable [%s] is not available in checkpoint',
                        variable_name)

    tf.train.init_from_checkpoint(ckpt_path, vars_in_ckpt)

    if force_restore_shape_compatible:
      return estimator_utils.IncompatibleShapeRestoreHook(
          incompatible_shape_var_map)
    else:
      return None

  def _get_restore_vars(self, ckpt_var_map_path):
    """Restore by specify variable map between graph variables and ckpt variables.

    Args:
      ckpt_var_map_path: variable map from graph variables to variables in a checkpoint
          each line consists of: variable name in graph  variable name in ckpt

    Returns:
      the list of variables which need to restore from checkpoint
    """
    # here must use global_variables, because variables such as moving_mean
    #  and moving_variance is usually not trainable in detection models
    all_vars = tf.global_variables()
    if ckpt_var_map_path != '':
      if not tf.gfile.Exists(ckpt_var_map_path):
        logging.warning('%s not exist' % ckpt_var_map_path)
        return {re.sub(':[0-9]$', '', var.name): var for var in all_vars}

      # load var map
      var_name_map = {}
      with open(ckpt_var_map_path, 'r') as fin:
        for one_line in fin:
          one_line = one_line.strip()
          line_tok = [x for x in one_line.split() if x != '']
          if len(line_tok) != 2:
            logging.warning('Failed to process: %s' % one_line)
            continue
          var_name_map[line_tok[0]] = line_tok[1]
      var_map = {}
      for one_var in all_vars:
        var_name = re.sub(':[0-9]$', '', one_var.name)
        if var_name in var_name_map:
          var_map[var_name_map[var_name]] = one_var
        elif 'Momentum' not in var_name:
          logging.warning('Failed to find in var_map_lst(%s): %s' %
                          (ckpt_var_map_path, var_name))
      return var_map
    else:
      var_filter, scope_update = self.get_restore_filter()
      if var_filter is not None:
        all_vars = [var for var in all_vars if var_filter.keep(var.name)]
      # drop scope prefix if necessary, in this case, return a dict
      if scope_update is not None:
        all_vars = {scope_update(var.name): var for var in all_vars}

      return {re.sub(':[0-9]$', '', var.name): var for var in all_vars}

  def get_restore_filter(self):
    """Get restore variable filter.

    Return:
       filter: type of Filter in restore_filter.py
       scope_drop: type of ScopeDrop in restore_filter.py
    """
    adam_filter = restore_filter.KeywordFilter('/Adam', True)
    momentum_filter = restore_filter.KeywordFilter('/Momentum', True)
    return restore_filter.CombineFilter([adam_filter, momentum_filter],
                                        restore_filter.Logical.AND), None