# -*- encoding:utf-8 -*-
# Copyright (c) Alibaba, Inc. and its affiliates.
"""Functions for reading and updating configuration files.

Such as Hyper parameter tuning or automatic feature expanding.
"""

import json
import logging
import os
import re

import tensorflow as tf
from google.protobuf import json_format
from google.protobuf import text_format
from tensorflow.python.lib.io import file_io

from easy_rec.python.protos import pipeline_pb2
from easy_rec.python.protos.feature_config_pb2 import FeatureConfig

if tf.__version__ >= '2.0':
  tf = tf.compat.v1


def get_configs_from_pipeline_file(pipeline_config_path, auto_expand=True):
  """Reads config from a file containing pipeline_pb2.EasyRecConfig.

  Args:
    pipeline_config_path: Path to pipeline_pb2.EasyRecConfig text
      proto.

  Returns:
    Dictionary of configuration objects. Keys are `model`, `train_config`,
      `train_input_config`, `eval_config`, `eval_input_config`. Value are the
      corresponding config objects.
  """
  if isinstance(pipeline_config_path, pipeline_pb2.EasyRecConfig):
    return pipeline_config_path

  assert tf.gfile.Exists(
      pipeline_config_path
  ), 'pipeline_config_path [%s] not exists' % pipeline_config_path

  pipeline_config = pipeline_pb2.EasyRecConfig()
  with tf.gfile.GFile(pipeline_config_path, 'r') as f:
    config_str = f.read()
    if pipeline_config_path.endswith('.config'):
      text_format.Merge(config_str, pipeline_config)
    elif pipeline_config_path.endswith('.json'):
      json_format.Parse(config_str, pipeline_config)
    else:
      assert False, 'invalid file format(%s), currently support formats: .config(prototxt) .json' % pipeline_config_path

  if auto_expand:
    return auto_expand_share_feature_configs(pipeline_config)
  else:
    return pipeline_config


def auto_expand_share_feature_configs(pipeline_config):
  for share_config in pipeline_config.feature_configs:
    if len(share_config.shared_names) == 0:
      continue

    # auto expand all shared_names
    input_names = []
    for input_name in share_config.shared_names:
      if pipeline_config.data_config.auto_expand_input_fields:
        input_names.extend(auto_expand_names(input_name))
      else:
        input_names.append(input_name)

    # make a clean copy
    while len(share_config.shared_names) > 0:
      share_config.shared_names.pop()

    fea_config = FeatureConfig()
    fea_config.CopyFrom(share_config)
    while len(fea_config.input_names) > 0:
      fea_config.input_names.pop()

    # generate for each item in input_name
    for tmp_name in input_names:
      tmp_config = FeatureConfig()
      tmp_config.CopyFrom(fea_config)
      tmp_config.input_names.append(tmp_name)
      pipeline_config.feature_configs.append(tmp_config)
  return pipeline_config


def auto_expand_names(input_name):
  """Auto expand field[1-3] to field1, field2, field3.

  Args:
    input_name: a string pattern like field[1-3]

  Returns:
    a string list of the expanded names
  Todo:
    could be extended to support more complicated patterns
  """
  match_obj = re.match(r'([a-zA-Z_]+)\[([0-9]+)-([0-9]+)\]', input_name)
  if match_obj:
    prefix = match_obj.group(1)
    sid = int(match_obj.group(2))
    eid = int(match_obj.group(3)) + 1
    input_name = ['%s%d' % (prefix, tid) for tid in range(sid, eid)]
  else:
    input_name = [input_name]
  return input_name


def create_pipeline_proto_from_configs(configs):
  """Creates a pipeline_pb2.EasyRecConfig from configs dictionary.

  This function performs the inverse operation of
  create_configs_from_pipeline_proto().

  Args:
    configs: Dictionary of configs. See get_configs_from_pipeline_file().

  Returns:
    A fully populated pipeline_pb2.EasyRecConfig.
  """
  pipeline_config = pipeline_pb2.EasyRecConfig()
  pipeline_config.model.CopyFrom(configs['model'])
  pipeline_config.train_config.CopyFrom(configs['train_config'])
  pipeline_config.train_input_reader.CopyFrom(configs['train_input_config'])
  pipeline_config.eval_config.CopyFrom(configs['eval_config'])
  pipeline_config.eval_input_reader.CopyFrom(configs['eval_input_config'])
  if 'graph_rewriter_config' in configs:
    pipeline_config.graph_rewriter.CopyFrom(configs['graph_rewriter_config'])
  return pipeline_config


def save_pipeline_config(pipeline_config,
                         directory,
                         filename='pipeline.config'):
  """Saves a pipeline config text file to disk.

  Args:
    pipeline_config: A pipeline_pb2.TrainEvalPipelineConfig.
    directory: The model directory into which the pipeline config file will be
      saved.
    filename: pipelineconfig filename
  """
  if not file_io.file_exists(directory):
    file_io.recursive_create_dir(directory)
  pipeline_config_path = os.path.join(directory, filename)
  # as_utf8=True to make sure pbtxt is human readable when string contains chinese
  save_message(pipeline_config, pipeline_config_path)


def edit_config(pipeline_config, edit_config_json):
  """Update params specified by automl.

  Args:
    pipeline_config: EasyRecConfig
    edit_config_json: edit config json
  """

  def _get_attr(obj, attr, only_last=False):
    # only_last means we only return the last element in paths array
    attr_toks = [x.strip() for x in attr.split('.') if x != '']
    paths = []
    objs = [obj]
    nobjs = []
    for key in attr_toks:
      # clear old paths to clear new paths
      paths = []
      for obj in objs:
        if '[' in key:
          pos = key.find('[')
          name, cond = key[:pos], key[pos + 1:]
          cond = cond[:-1]
          update_objs = getattr(obj, name)
          # select all update_objs
          if cond == ':':
            for tid, update_obj in enumerate(update_objs):
              paths.append((obj, update_obj, None, tid))
              nobjs.append(update_obj)
            continue

          # select by range update_objs[1:10]
          if ':' in cond:
            colon_pos = cond.find(':')
            sid = cond[:colon_pos]
            if len(sid) == 0:
              sid = 0
            else:
              sid = int(sid)
            eid = cond[(colon_pos + 1):]
            if len(eid) == 0:
              eid = len(update_objs)
            else:
              eid = int(eid)
            for tid, update_obj in enumerate(update_objs[sid:eid]):
              paths.append((obj, update_obj, None, tid + sid))
              nobjs.append(update_obj)
            continue

          # for simple index update_objs[0]
          try:
            obj_id = int(cond)
            obj = update_objs[obj_id]
            paths.append((obj, update_objs, None, obj_id))
            nobjs.append(obj)
            continue
          except ValueError:
            pass

          # for complex conditions a[optimizer.lr=20]
          op_func_map = {
              '>=': lambda x, y: x >= y,
              '<=': lambda x, y: x <= y,
              '<': lambda x, y: x < y,
              '>': lambda x, y: x > y,
              '=': lambda x, y: x == y
          }
          cond_key = None
          cond_val = None
          op_func = None
          for op in ['>=', '<=', '>', '<', '=']:
            tmp_pos = cond.rfind(op)
            if tmp_pos != -1:
              cond_key = cond[:tmp_pos]
              cond_val = cond[(tmp_pos + len(op)):]
              op_func = op_func_map[op]
              break

          assert cond_key is not None, 'invalid cond: %s' % cond
          assert cond_val is not None, 'invalid cond: %s' % cond

          for tid, update_obj in enumerate(update_objs):
            tmp, tmp_parent, _, _ = _get_attr(
                update_obj, cond_key, only_last=True)
            if type(cond_val) != type(tmp):
              try:
                cond_val = type(tmp)(cond_val)
              except ValueError:
                # to support for enumerations like IdFeature
                assert isinstance(tmp, int)
                cond_val = getattr(tmp_parent, cond_val)
                assert isinstance(cond_val, int)
            if op_func(tmp, cond_val):
              obj_id = tid
              paths.append((update_obj, update_objs, None, obj_id))
              nobjs.append(update_obj)
        else:
          sub_obj = getattr(obj, key)
          paths.append((sub_obj, obj, key, -1))
          nobjs.append(sub_obj)
      # exchange to prepare for parsing next token
      objs = nobjs
      nobjs = []
    if only_last:
      return paths[-1]
    else:
      return paths

  for param_keys in edit_config_json:
    # multiple keys/vals combination
    param_vals = edit_config_json[param_keys]
    param_vals = [x.strip() for x in str(param_vals).split(';')]
    param_keys = [x.strip() for x in str(param_keys).split(';')]
    for param_key, param_val in zip(param_keys, param_vals):
      update_obj = pipeline_config
      tmp_paths = _get_attr(update_obj, param_key)
      # update a set of objs
      for tmp_val, tmp_obj, tmp_name, tmp_id in tmp_paths:
        basic_types = [int, str, float, bool, type(u'')]
        if type(tmp_val) in basic_types:
          # simple type cast
          try:
            tmp_val = type(tmp_val)(param_val)
            if tmp_name is None:
              tmp_obj[tmp_id] = tmp_val
            else:
              setattr(tmp_obj, tmp_name, tmp_val)
          except ValueError:
            # for enumeration types
            text_format.Merge('%s:%s' % (tmp_name, param_val), tmp_obj)
        elif 'Scalar' in str(type(tmp_val)) and 'ClearField' in dir(tmp_obj):
          tmp_obj.ClearField(tmp_name)
          text_format.Parse('%s:%s' % (tmp_name, param_val), tmp_obj)
        else:
          tmp_val.Clear()
          param_val = param_val.strip()
          if param_val.startswith('{') and param_val.endswith('}'):
            param_val = param_val[1:-1]
          text_format.Parse(param_val, tmp_val)

  return pipeline_config


def save_message(protobuf_message, filename):
  """Saves a pipeline config text file to disk.

  Args:
    protobuf_message: A pipeline_pb2.TrainEvalPipelineConfig.
    filename: pipeline config filename
  """
  directory, _ = os.path.split(filename)
  if not file_io.file_exists(directory):
    file_io.recursive_create_dir(directory)
  # as_utf8=True to make sure pbtxt is human readable when string contains chinese
  config_text = text_format.MessageToString(protobuf_message, as_utf8=True)
  with tf.gfile.Open(filename, 'wb') as f:
    logging.info('Writing protobuf message file to %s', filename)
    f.write(config_text)


def add_boundaries_to_config(pipeline_config, tables):
  import common_io

  feature_boundaries_info = {}
  reader = common_io.table.TableReader(tables, selected_cols='feature,json')
  while True:
    try:
      record = reader.read()
      raw_info = json.loads(record[0][1])
      bin_info = []
      for info in raw_info['bin']['norm'][:-1]:
        split_point = float(info['value'].split(',')[1][:-1])
        bin_info.append(split_point)
      feature_boundaries_info[record[0][0]] = bin_info
    except common_io.exception.OutOfRangeException:
      reader.close()
      break

  logging.info('feature boundaries: %s' % feature_boundaries_info)

  for feature_config in pipeline_config.feature_configs:
    feature_name = feature_config.input_names[0]
    if feature_name in feature_boundaries_info:
      feature_config.feature_type = feature_config.RawFeature
      feature_config.hash_bucket_size = 0
      feature_config.ClearField('boundaries')
      feature_config.boundaries.extend(feature_boundaries_info[feature_name])
      logging.info('edited %s' % feature_name)
