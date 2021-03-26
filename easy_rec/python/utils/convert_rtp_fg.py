# -*- encoding:utf-8 -*-
# Copyright (c) Alibaba, Inc. and its affiliates.
import json
import logging
import sys

import tensorflow as tf
from google.protobuf import text_format

from easy_rec.python.protos.dataset_pb2 import DatasetConfig
from easy_rec.python.protos.feature_config_pb2 import FeatureConfig
from easy_rec.python.protos.feature_config_pb2 import FeatureGroupConfig
from easy_rec.python.protos.feature_config_pb2 import WideOrDeep
from easy_rec.python.protos.pipeline_pb2 import EasyRecConfig
from easy_rec.python.utils import config_util

if tf.__version__ >= '2.0':
  tf = tf.compat.v1


def _gen_raw_config(feature, input_field, feature_config, is_multi,
                    curr_embed_dim):
  if 'bucketize_boundaries' in feature:
    if is_multi:
      input_field.input_type = DatasetConfig.STRING
      feature_config.feature_type = feature_config.TagFeature
    else:
      input_field.input_type = DatasetConfig.INT32
      feature_config.feature_type = feature_config.IdFeature
    feature_config.num_buckets = len(
        feature['bucketize_boundaries'].split(',')) + 1
    feature_config.embedding_dim = curr_embed_dim
  else:
    feature_config.feature_type = feature_config.RawFeature
    input_field.default_val = '0.0'
    raw_input_dim = feature.get('value_dimension', 1)
    if raw_input_dim > 1:
      feature_config.raw_input_dim = raw_input_dim
      input_field.input_type = DatasetConfig.STRING
    else:
      input_field.input_type = DatasetConfig.DOUBLE
    if 'boundaries' in feature:
      feature_config.boundaries.extend(feature['boundaries'])
      feature_config.embedding_dim = curr_embed_dim


def _set_hash_bucket(feature, feature_config, input_field):
  if 'hash_bucket_size' in feature:
    feature_config.hash_bucket_size = feature['hash_bucket_size']
  elif 'vocab_file' in feature:
    feature_config.vocab_file = feature['vocab_file']
  elif 'vocab_list' in feature:
    feature_config.vocab_list = feature['vocab_list']
  elif 'num_buckets' in feature:
    feature_config.num_buckets = feature['num_buckets']
    input_field.default_val = '0'
  else:
    assert False, 'one of hash_bucket_size,vocab_file,vocab_list,num_buckets must be set'


def convert_rtp_fg(rtp_fg,
                   embedding_dim=16,
                   batch_size=1024,
                   label_fields=[],
                   num_steps=10,
                   model_type='',
                   separator='\002',
                   incol_separator='\003',
                   train_input_path=None,
                   eval_input_path=None,
                   selected_cols='',
                   input_type='OdpsRTPInput'):
  with tf.gfile.GFile(rtp_fg, 'r') as fin:
    rtp_fg = json.load(fin)

  model_dir = rtp_fg.get('model_dir', 'experiments/rtp_fg_demo')
  num_steps = rtp_fg.get('num_steps', num_steps)
  model_type = rtp_fg.get('model_type', model_type)
  embedding_dim = rtp_fg.get('embedding_dim', embedding_dim)
  label_fields = rtp_fg.get('label_fields', label_fields)
  model_path = rtp_fg.get('model_path', '')
  edit_config_json = rtp_fg.get('edit_config_json', None)

  logging.info('model_dir = %s' % model_dir)
  logging.info('num_steps = %d' % num_steps)
  logging.info('model_type = %s' % model_type)
  logging.info('embedding_dim = %s' % embedding_dim)
  logging.info('label_fields = %s' % ','.join(label_fields))
  logging.info('model_path = %s' % model_path)
  logging.info('edit_config_json = %s' % edit_config_json)

  pipeline_config = EasyRecConfig()

  for tmp_lbl in label_fields:
    input_field = DatasetConfig.Field()
    input_field.input_name = tmp_lbl
    input_field.input_type = DatasetConfig.INT32
    input_field.default_val = '0'
    pipeline_config.data_config.input_fields.append(input_field)

  pipeline_config.data_config.separator = separator
  if selected_cols:
    pipeline_config.data_config.selected_cols = selected_cols
  if train_input_path is not None:
    pipeline_config.train_input_path = train_input_path
  if eval_input_path is not None:
    pipeline_config.eval_input_path = eval_input_path

  pipeline_config.model_dir = model_dir

  rtp_features = rtp_fg['features']
  for feature in rtp_features:
    try:
      feature_type = feature['feature_type']
      feature_name = feature['feature_name']
      feature_config = FeatureConfig()
      feature_config.input_names.append(feature_name)
      feature_config.separator = incol_separator
      input_field = DatasetConfig.Field()
      input_field.input_name = feature_name
      curr_embed_dim = feature.get('embedding_dimension',
                                   feature.get('embedding_dim', embedding_dim))
      curr_combiner = feature.get('combiner', 'mean')
      if feature.get('is_cache', False):
        logging.info('will cache %s' % feature_name)
        feature_config.is_cache = True
      is_multi = feature.get('is_multi', False)
      if feature_type == 'id_feature':
        if is_multi:
          feature_config.feature_type = feature_config.TagFeature
        else:
          feature_config.feature_type = feature_config.IdFeature
        feature_config.embedding_dim = curr_embed_dim
        _set_hash_bucket(feature, feature_config, input_field)
        feature_config.combiner = curr_combiner
      elif feature_type == 'lookup_feature':
        need_discrete = feature.get('needDiscrete', True)
        if not need_discrete:
          _gen_raw_config(feature, input_field, feature_config, is_multi,
                          curr_embed_dim)
        else:
          if is_multi:
            feature_config.feature_type = feature_config.TagFeature
            if feature_config.get('needWeighting', False):
              feature_config.kv_separator = ''
          else:
            feature_config.feature_type = feature_config.IdFeature
          feature_config.embedding_dim = curr_embed_dim
          _set_hash_bucket(feature, feature_config, input_field)
          feature_config.combiner = curr_combiner
      elif feature_type == 'raw_feature':
        _gen_raw_config(feature, input_field, feature_config, is_multi,
                        curr_embed_dim)
      elif feature_type == 'match_feature':
        need_discrete = feature.get('needDiscrete', True)
        if feature.get('matchType', '') == 'multihit':
          is_multi = True
        if need_discrete:
          if is_multi:
            feature_config.feature_type = feature_config.TagFeature
            if feature_config.get('needWeighting', False):
              feature_config.kv_separator = ''
          else:
            feature_config.feature_type = feature_config.IdFeature
          feature_config.embedding_dim = curr_embed_dim
          _set_hash_bucket(feature, feature_config, input_field)
          feature_config.combiner = curr_combiner
        else:
          assert 'bucketize_boundaries' not in feature
          _gen_raw_config(feature, input_field, feature_config, is_multi,
                          curr_embed_dim)
      elif feature_type == 'combo_feature':
        feature_config.feature_type = feature_config.TagFeature
        _set_hash_bucket(feature, feature_config, input_field)
        feature_config.embedding_dim = curr_embed_dim
        feature_config.combiner = curr_combiner
      elif feature_type == 'overlap_feature':
        if feature['method'] in ['common_word_divided', 'diff_word_divided']:
          feature_config.feature_type = feature_config.TagFeature
        else:
          feature_config.feature_type = feature_config.IdFeature
        _set_hash_bucket(feature, feature_config, input_field)
        feature_config.embedding_dim = curr_embed_dim
        feature_config.combiner = curr_combiner
      elif feature_type == 'expr_feature':
        feature_config.feature_type = feature_config.RawFeature
        input_field.input_type = DatasetConfig.DOUBLE
        input_field.default_val = '0.0'
      else:
        assert 'unknown feature type %s, currently not supported' % feature_type
      if 'shared_name' in feature:
        feature_config.embedding_name = feature['shared_name']
      pipeline_config.feature_configs.append(feature_config)
      pipeline_config.data_config.input_fields.append(input_field)
    except Exception as ex:
      print('Exception: %s %s' % (type(ex), str(ex)))
      print(feature)
      sys.exit(1)
  pipeline_config.data_config.batch_size = batch_size
  pipeline_config.data_config.rtp_separator = ';'
  pipeline_config.data_config.label_fields.extend(label_fields)

  text_format.Merge('input_type: %s' % input_type, pipeline_config.data_config)

  if model_path:
    model_type = None
    with tf.gfile.GFile(model_path, 'r') as fin:
      model_config = fin.read()
      text_format.Merge(model_config, pipeline_config)

  if not pipeline_config.HasField('train_config'):
    train_config_str = """
    train_config {
      log_step_count_steps: 200
      optimizer_config: {
        adam_optimizer: {
          learning_rate: {
            exponential_decay_learning_rate {
              initial_learning_rate: 0.0001
              decay_steps: 100000
              decay_factor: 0.5
              min_learning_rate: 0.0000001
            }
          }
        }
        use_moving_average: false
      }

      sync_replicas: true
    }
    """
    text_format.Merge(train_config_str, pipeline_config)

  pipeline_config.train_config.num_steps = num_steps

  if model_type == 'deepfm':
    pipeline_config.model_config.model_class = 'DeepFM'
    wide_group = FeatureGroupConfig()
    wide_group.group_name = 'wide'
    wide_group.wide_deep = WideOrDeep.WIDE
    for feature in rtp_features:
      feature_name = feature['feature_name']
      wide_group.feature_names.append(feature_name)
    pipeline_config.model_config.feature_groups.append(wide_group)
    deep_group = FeatureGroupConfig()
    deep_group.CopyFrom(wide_group)
    deep_group.group_name = 'deep'
    deep_group.wide_deep = WideOrDeep.DEEP
    pipeline_config.model_config.feature_groups.append(deep_group)
    deepfm_config_str = """
    deepfm {
      dnn {
        hidden_units: [128, 64, 32]
      }
      final_dnn {
        hidden_units: [128, 64]
      }
      wide_output_dim: 32
      l2_regularization: 1e-5
    }
    """
    text_format.Merge(deepfm_config_str, pipeline_config.model_config)
    pipeline_config.model_config.embedding_regularization = 1e-5
  elif model_type == 'wide_and_deep':
    pipeline_config.model_config.model_class = 'WideAndDeep'
    wide_group = FeatureGroupConfig()
    wide_group.group_name = 'wide'
    wide_group.wide_deep = WideOrDeep.WIDE
    for feature in rtp_features:
      feature_name = feature['feature_name']
      group = feature.get('group', 'wide_and_deep')
      if group not in ['wide', 'deep', 'wide_and_deep']:
        logging.warning('invalid group %s for %s' % (group, feature_name))
        group = 'wide_and_deep'
      if group in ['wide', 'wide_and_deep']:
        wide_group.feature_names.append(feature_name)
    pipeline_config.model_config.feature_groups.append(wide_group)
    deep_group = FeatureGroupConfig()
    deep_group.group_name = 'deep'
    deep_group.wide_deep = WideOrDeep.DEEP
    for feature in rtp_features:
      feature_name = feature['feature_name']
      group = feature.get('group', 'wide_and_deep')
      if group not in ['wide', 'deep', 'wide_and_deep']:
        group = 'wide_and_deep'
      if group in ['deep', 'wide_and_deep']:
        deep_group.feature_names.append(feature_name)
    pipeline_config.model_config.feature_groups.append(deep_group)
    deepfm_config_str = """
    wide_and_deep {
      dnn {
        hidden_units: [128, 64, 32]
      }
      l2_regularization: 1e-5
    }
    """
    text_format.Merge(deepfm_config_str, pipeline_config.model_config)
    pipeline_config.model_config.embedding_regularization = 1e-5
  elif model_type == 'multi_tower':
    pipeline_config.model_config.model_class = 'MultiTower'

    feature_groups = {}
    group_map = {
        'u': 'user',
        'i': 'item',
        'ctx': 'combo',
        'q': 'combo',
        'comb': 'combo'
    }
    for feature in rtp_features:
      feature_name = feature['feature_name'].strip()
      group_name = ''
      if 'group' in feature:
        group_name = feature['group']
      else:
        toks = feature_name.split('_')
        group_name = toks[0]
        if group_name in group_map:
          group_name = group_map[group_name]
      if group_name in feature_groups:
        feature_groups[group_name].append(feature_name)
      else:
        feature_groups[group_name] = [feature_name]

    logging.info(
        'if group is specified, group will be used as feature group name; '
        'otherwise, the prefix of feature_name in fg.json is used as feature group name'
    )
    logging.info('prefix map: %s' % str(group_map))
    for group_name in feature_groups:
      logging.info('add group = %s' % group_name)
      group = FeatureGroupConfig()
      group.group_name = group_name
      for fea_name in feature_groups[group_name]:
        group.feature_names.append(fea_name)
      group.wide_deep = WideOrDeep.DEEP
      pipeline_config.model_config.feature_groups.append(group)

    multi_tower_config_str = '  multi_tower {\n'
    for group_name in feature_groups:
      multi_tower_config_str += """
      towers {
        input: "%s"
        dnn {
          hidden_units: [256, 192, 128]
        }
      }
      """ % group_name

    multi_tower_config_str = multi_tower_config_str + """
      final_dnn {
        hidden_units: [192, 128, 64]
      }
      l2_regularization: 1e-4
    }
    """
    text_format.Merge(multi_tower_config_str, pipeline_config.model_config)
    pipeline_config.model_config.embedding_regularization = 1e-5
    text_format.Merge("""
    metrics_set {
      auc {}
    }
    """, pipeline_config.eval_config)

  text_format.Merge(
      """
    export_config {
      multi_placeholder: false
    }
  """, pipeline_config)

  if edit_config_json:
    for edit_obj in edit_config_json:
      config_util.edit_config(pipeline_config, edit_obj)

  return pipeline_config
