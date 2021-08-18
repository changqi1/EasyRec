# -*- encoding:utf-8 -*-
# Copyright (c) Alibaba, Inc. and its affiliates.
import logging

import tensorflow as tf

from easy_rec.python.utils.load_class import load_by_path

if tf.__version__ >= '2.0':
  tf = tf.compat.v1


class DNN:

  def __init__(self, dnn_config, l2_reg, name='dnn', is_training=False):
    """Initializes a `DNN` Layer.

    Args:
      dnn_config: instance of easy_rec.python.protos.dnn_pb2.DNN
      l2_reg: l2 regularizer
      name: scope of the DNN, so that the parameters could be separated from other dnns
      is_training: train phase or not, impact batchnorm and dropout
    """
    self._config = dnn_config
    self._l2_reg = l2_reg
    self._name = name
    self._is_training = is_training
    logging.info('dnn activation function = %s' % self._config.activation)
    self.activation = load_by_path(self._config.activation)

  @property
  def hidden_units(self):
    return self._config.hidden_units

  @property
  def dropout_ratio(self):
    return self._config.dropout_ratio

  def __call__(self, deep_fea, hidden_layer_feature_output=False):
    hidden_units_len = len(self.hidden_units)
    hidden_feature_dict = {}
    for i, unit in enumerate(self.hidden_units):
      deep_fea = tf.layers.dense(
          inputs=deep_fea,
          units=unit,
          kernel_regularizer=self._l2_reg,
          activation=None,
          name='%s/dnn_%d' % (self._name, i))
      if self._config.use_bn:
        deep_fea = tf.layers.batch_normalization(
            deep_fea,
            training=self._is_training,
            trainable=True,
            name='%s/dnn_%d/bn' % (self._name, i))
      deep_fea = self.activation(
          deep_fea, name='%s/dnn_%d/act' % (self._name, i))
      if len(self.dropout_ratio) > 0 and self._is_training:
        assert self.dropout_ratio[
            i] < 1, 'invalid dropout_ratio: %.3f' % self.dropout_ratio[i]
        deep_fea = tf.nn.dropout(
            deep_fea,
            keep_prob=1 - self.dropout_ratio[i],
            name='%s/%d/dropout' % (self._name, i))

      if hidden_layer_feature_output:
        hidden_feature_dict['hidden_layer' + str(i)] = deep_fea
        if (i + 1 == hidden_units_len):
          hidden_feature_dict['hidden_layer_end'] = deep_fea
          return hidden_feature_dict
    else:
      return deep_fea
