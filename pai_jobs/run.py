# -*- encoding:utf-8 -*-
# Copyright (c) Alibaba, Inc. and its affiliates.
from __future__ import print_function

import json
import logging
import os

import tensorflow as tf

import easy_rec
from easy_rec.python.inference.predictor import Predictor
from easy_rec.python.protos.train_pb2 import DistributionStrategy
from easy_rec.python.utils import config_util
from easy_rec.python.utils import estimator_utils
from easy_rec.python.utils import hpo_util
from easy_rec.python.utils import pai_util
from easy_rec.python.utils.estimator_utils import chief_to_master
from easy_rec.python.utils.estimator_utils import master_to_chief

if not tf.__version__.startswith('1.12'):
  tf = tf.compat.v1
  try:
    import tensorflow_io as tfio  # noqa: F401
  except Exception as ex:
    logging.error('failed to import tfio: %s' % str(ex))
  tf.disable_eager_execution()

from easy_rec.python.main import _train_and_evaluate_impl as train_and_evaluate_impl  # NOQA

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s][%(levelname)s] %(message)s')

tf.app.flags.DEFINE_string('worker_hosts', '',
                           'Comma-separated list of hostname:port pairs')
tf.app.flags.DEFINE_string('ps_hosts', '',
                           'Comma-separated list of hostname:port pairs')
tf.app.flags.DEFINE_string('job_name', '', 'task type, ps/worker')
tf.app.flags.DEFINE_integer('task_index', 0, 'Index of task within the job')
tf.app.flags.DEFINE_string('config', '', 'EasyRec config file path')
tf.app.flags.DEFINE_string('cmd', 'train',
                           'command type, train/evaluate/export')
tf.app.flags.DEFINE_string('tables', '', 'tables passed by pai command')

# flags for train
tf.app.flags.DEFINE_integer('num_gpus_per_worker', 1,
                            'number of gpu to use in training')
tf.app.flags.DEFINE_boolean('with_evaluator', False,
                            'whether a evaluator is necessary')
tf.app.flags.DEFINE_string(
    'eval_method', 'none', 'default to none, choices are [none: not evaluate,' +
    'master: evaluate on master, separate: evaluate on a separate task]')

tf.app.flags.DEFINE_string('distribute_strategy', '',
                           'training distribute strategy')
tf.app.flags.DEFINE_string('edit_config_json', '', 'edit config json string')
tf.app.flags.DEFINE_string('train_tables', '', 'tables used for train')
tf.app.flags.DEFINE_string('eval_tables', '', 'tables used for evaluation')
tf.app.flags.DEFINE_string('boundary_table', '', 'tables used for boundary')
tf.app.flags.DEFINE_string('sampler_table', '', 'tables used for sampler')

# flags used for evaluate & export
tf.app.flags.DEFINE_string(
    'checkpoint_path', '', 'checkpoint to be evaluated or exported '
    'if not specified, use the latest checkpoint '
    'in train_config.model_dir')
# flags used for evaluate
tf.app.flags.DEFINE_string('eval_result_path', 'eval_result.txt',
                           'eval result metric file')
# flags used for export
tf.app.flags.DEFINE_string('export_dir', '',
                           'directory where model should be exported to')
tf.app.flags.DEFINE_boolean('continue_train', True,
                            'use the same model to continue train or not')

# flags used for predict
tf.app.flags.DEFINE_string('saved_model_dir', '',
                           'directory where saved_model.pb exists')
tf.app.flags.DEFINE_string('outputs', '', 'output tables')
tf.app.flags.DEFINE_string(
    'all_cols', '',
    'union of (selected_cols, reserved_cols), separated with , ')
tf.app.flags.DEFINE_string(
    'all_col_types', '',
    'column data types, for build record defaults, separated with ,')
tf.app.flags.DEFINE_string(
    'selected_cols', '',
    'columns to keep from input table,  they are separated with ,')
tf.app.flags.DEFINE_string(
    'reserved_cols', '',
    'columns to keep from input table,  they are separated with ,')
tf.app.flags.DEFINE_string(
    'output_cols', None,
    'output columns, such as: score float. multiple columns are separated by ,')
tf.app.flags.DEFINE_integer('batch_size', 1024, 'predict batch size')
tf.app.flags.DEFINE_string(
    'profiling_file', None,
    'time stat file which can be viewed using chrome tracing')
tf.app.flags.DEFINE_string('redis_url', None, 'export to redis url, host:port')
tf.app.flags.DEFINE_string('redis_passwd', None, 'export to redis passwd')
tf.app.flags.DEFINE_integer('redis_threads', 5, 'export to redis threads')
tf.app.flags.DEFINE_integer('redis_batch_size', 1024,
                            'export to redis batch_size')
tf.app.flags.DEFINE_integer('redis_timeout', 600,
                            'export to redis time_out in seconds')
tf.app.flags.DEFINE_integer('redis_expire', 24,
                            'export to redis expire time in hour')
tf.app.flags.DEFINE_string('redis_embedding_version', '',
                           'redis embedding version')
tf.app.flags.DEFINE_integer('redis_write_kv', 1, 'whether write kv ')
tf.app.flags.DEFINE_bool('verbose', False, 'print more debug information')

# for automl hyper parameter tuning
tf.app.flags.DEFINE_string('model_dir', None, 'model directory')
tf.app.flags.DEFINE_string('hpo_param_path', None,
                           'hyperparameter tuning param path')
tf.app.flags.DEFINE_string('hpo_metric_save_path', None,
                           'hyperparameter save metric path')
tf.app.flags.DEFINE_string('asset_files', None, 'extra files to add to export')

FLAGS = tf.app.flags.FLAGS


def check_param(name):
  assert getattr(FLAGS, name) != '', '%s should not be empty' % name


DistributionStrategyMap = {
    '': DistributionStrategy.NoStrategy,
    'ps': DistributionStrategy.PSStrategy,
    'ess': DistributionStrategy.ExascaleStrategy,
    'mirrored': DistributionStrategy.MirroredStrategy,
    'collective': DistributionStrategy.CollectiveAllReduceStrategy
}


def set_tf_config_and_get_train_worker_num(
    distribute_strategy=DistributionStrategy.NoStrategy, eval_method='none'):
  logging.info(
      'set_tf_config_and_get_train_worker_num: distribute_strategy = %d' %
      distribute_strategy)
  worker_hosts = FLAGS.worker_hosts.split(',')
  ps_hosts = FLAGS.ps_hosts.split(',')

  total_worker_num = len(worker_hosts)
  train_worker_num = total_worker_num

  print('Original TF_CONFIG=%s' % os.environ.get('TF_CONFIG', ''))
  print('worker_hosts=%s ps_hosts=%s task_index=%d job_name=%s' %
        (FLAGS.worker_hosts, FLAGS.ps_hosts, FLAGS.task_index, FLAGS.job_name))
  print('eval_method=%s' % eval_method)
  if distribute_strategy == DistributionStrategy.MirroredStrategy:
    assert total_worker_num == 1, 'mirrored distribute strategy only need 1 worker'
  elif distribute_strategy in [
      DistributionStrategy.NoStrategy, DistributionStrategy.PSStrategy,
      DistributionStrategy.CollectiveAllReduceStrategy,
      DistributionStrategy.ExascaleStrategy
  ]:
    cluster, task_type, task_index = estimator_utils.parse_tf_config()
    train_worker_num = 0
    if eval_method == 'separate':
      if 'evaluator' in cluster:
        # 'evaluator' in cluster indicates user use new-style cluster content
        if 'chief' in cluster:
          train_worker_num += len(cluster['chief'])
        elif 'master' in cluster:
          train_worker_num += len(cluster['master'])
        if 'worker' in cluster:
          train_worker_num += len(cluster['worker'])
        # drop evaluator to avoid hang
        if distribute_strategy == DistributionStrategy.NoStrategy:
          del cluster['evaluator']
        tf_config = {
            'cluster': cluster,
            'task': {
                'type': task_type,
                'index': task_index
            }
        }
        os.environ['TF_CONFIG'] = json.dumps(tf_config)
      else:
        # backward compatibility, if user does not assign one evaluator in
        # -Dcluster, we use first worker for chief, second for evaluation
        train_worker_num = total_worker_num - 1
        assert train_worker_num > 0, 'in distribution mode worker num must be greater than 1, ' \
                                     'the second worker will be used as evaluator'
        if len(worker_hosts) > 1:
          cluster = {'chief': [worker_hosts[0]], 'worker': worker_hosts[2:]}
          if distribute_strategy != DistributionStrategy.NoStrategy:
            cluster['evaluator'] = [worker_hosts[1]]
          if FLAGS.ps_hosts != '':
            cluster['ps'] = ps_hosts
          if FLAGS.job_name == 'ps':
            os.environ['TF_CONFIG'] = json.dumps({
                'cluster': cluster,
                'task': {
                    'type': FLAGS.job_name,
                    'index': FLAGS.task_index
                }
            })
          elif FLAGS.job_name == 'worker':
            if FLAGS.task_index == 0:
              os.environ['TF_CONFIG'] = json.dumps({
                  'cluster': cluster,
                  'task': {
                      'type': 'chief',
                      'index': 0
                  }
              })
            elif FLAGS.task_index == 1:
              os.environ['TF_CONFIG'] = json.dumps({
                  'cluster': cluster,
                  'task': {
                      'type': 'evaluator',
                      'index': 0
                  }
              })
            else:
              os.environ['TF_CONFIG'] = json.dumps({
                  'cluster': cluster,
                  'task': {
                      'type': FLAGS.job_name,
                      'index': FLAGS.task_index - 2
                  }
              })
    else:
      if 'evaluator' in cluster:
        evaluator = cluster['evaluator']
        del cluster['evaluator']
        # 'evaluator' in cluster indicates user use new-style cluster content
        train_worker_num += 1
        if 'chief' in cluster:
          train_worker_num += len(cluster['chief'])
        elif 'master' in cluster:
          train_worker_num += len(cluster['master'])
        if 'worker' in cluster:
          train_worker_num += len(cluster['worker'])
          cluster['worker'].append(evaluator[0])
        else:
          cluster['worker'] = [evaluator[0]]
        if task_type == 'evaluator':
          tf_config = {
              'cluster': cluster,
              'task': {
                  'type': 'worker',
                  'index': train_worker_num - 2
              }
          }
        else:
          tf_config = {
              'cluster': cluster,
              'task': {
                  'type': task_type,
                  'index': task_index
              }
          }
        os.environ['TF_CONFIG'] = json.dumps(tf_config)
      else:
        cluster = {'chief': [worker_hosts[0]], 'worker': worker_hosts[1:]}
        train_worker_num = len(worker_hosts)
        if FLAGS.ps_hosts != '':
          cluster['ps'] = ps_hosts
        if FLAGS.job_name == 'ps':
          os.environ['TF_CONFIG'] = json.dumps({
              'cluster': cluster,
              'task': {
                  'type': FLAGS.job_name,
                  'index': FLAGS.task_index
              }
          })
        else:
          if FLAGS.task_index == 0:
            os.environ['TF_CONFIG'] = json.dumps({
                'cluster': cluster,
                'task': {
                    'type': 'chief',
                    'index': 0
                }
            })
          else:
            os.environ['TF_CONFIG'] = json.dumps({
                'cluster': cluster,
                'task': {
                    'type': 'worker',
                    'index': FLAGS.task_index - 1
                }
            })
      if eval_method == 'none':
        # change master to chief, will not evaluate
        master_to_chief()
      elif eval_method == 'master':
        # change chief to master, will evaluate on master
        chief_to_master()
  else:
    assert distribute_strategy == '', 'invalid distribute_strategy %s'\
           % distribute_strategy
    cluster, task_type, task_index = estimator_utils.parse_tf_config()
  print('Final TF_CONFIG = %s' % os.environ.get('TF_CONFIG', ''))
  tf.logging.info('TF_CONFIG %s' % os.environ.get('TF_CONFIG', ''))
  tf.logging.info('distribute_stategy %s, train_worker_num: %d' %
                  (distribute_strategy, train_worker_num))

  # remove pai chief-worker waiting strategy
  # which is conflicted with worker waiting strategy in easyrec
  if 'TF_WRITE_WORKER_STATUS_FILE' in os.environ:
    del os.environ['TF_WRITE_WORKER_STATUS_FILE']
  return train_worker_num


def set_distribution_config(pipeline_config, num_worker, num_gpus_per_worker,
                            distribute_strategy):
  if distribute_strategy in [
      DistributionStrategy.PSStrategy, DistributionStrategy.MirroredStrategy,
      DistributionStrategy.CollectiveAllReduceStrategy,
      DistributionStrategy.ExascaleStrategy
  ]:
    pipeline_config.train_config.sync_replicas = False
    pipeline_config.train_config.train_distribute = distribute_strategy
    pipeline_config.train_config.num_gpus_per_worker = num_gpus_per_worker
  print('Dump pipeline_config.train_config:')
  print(pipeline_config.train_config)


def set_selected_cols(pipeline_config, selected_cols, all_cols, all_col_types):
  if selected_cols:
    pipeline_config.data_config.selected_cols = selected_cols
    # add column types which will be used by OdpsInput, OdpsInputV2
    # to check consistency with input_fields.input_type
    if all_cols:
      all_cols_arr = all_cols.split(',')
      all_col_types_arr = all_col_types.split(',')
      all_col_types_map = {
          x.strip(): y.strip() for x, y in zip(all_cols_arr, all_col_types_arr)
      }
      selected_cols_arr = [x.strip() for x in selected_cols.split(',')]
      selected_col_types = [all_col_types_map[x] for x in selected_cols_arr]
      selected_col_types = ','.join(selected_col_types)
      pipeline_config.data_config.selected_col_types = selected_col_types

  print('[run.py] data_config.selected_cols = "%s"' %
        pipeline_config.data_config.selected_cols)
  print('[run.py] data_config.selected_col_types = "%s"' %
        pipeline_config.data_config.selected_col_types)


def main(argv):
  pai_util.set_on_pai()
  num_gpus_per_worker = FLAGS.num_gpus_per_worker
  worker_hosts = FLAGS.worker_hosts.split(',')
  num_worker = len(worker_hosts)
  assert FLAGS.distribute_strategy in DistributionStrategyMap, \
      'invalid distribute_strategy [%s], available ones are %s' % (
          FLAGS.distribute_strategy, ','.join(DistributionStrategyMap.keys()))

  if FLAGS.config:
    config = pai_util.process_config(FLAGS.config, FLAGS.task_index,
                                     len(FLAGS.worker_hosts.split(',')))
    pipeline_config = config_util.get_configs_from_pipeline_file(config, False)

  if FLAGS.edit_config_json:
    print('[run.py] edit_config_json = %s' % FLAGS.edit_config_json)
    config_json = json.loads(FLAGS.edit_config_json)
    config_util.edit_config(pipeline_config, config_json)

  if FLAGS.model_dir:
    pipeline_config.model_dir = FLAGS.model_dir
    pipeline_config.model_dir = pipeline_config.model_dir.strip()
    print('[run.py] update model_dir to %s' % pipeline_config.model_dir)
    assert pipeline_config.model_dir.startswith(
        'oss://'), 'invalid model_dir format: %s' % pipeline_config.model_dir

  if FLAGS.cmd == 'train':
    assert FLAGS.config, 'config should not be empty when training!'

    if not FLAGS.train_tables:
      tables = FLAGS.tables.split(',')
      assert len(
          tables
      ) >= 2, 'at least 2 tables must be specified, but only[%d]: %s' % (
          len(tables), FLAGS.tables)

    if FLAGS.train_tables:
      pipeline_config.train_input_path = FLAGS.train_tables
    else:
      pipeline_config.train_input_path = FLAGS.tables.split(',')[0]

    if FLAGS.eval_tables:
      pipeline_config.eval_input_path = FLAGS.eval_tables
    else:
      pipeline_config.eval_input_path = FLAGS.tables.split(',')[1]

    print('[run.py] train_tables: %s' % pipeline_config.train_input_path)
    print('[run.py] eval_tables: %s' % pipeline_config.eval_input_path)

    if FLAGS.boundary_table:
      logging.info('Load boundary_table: %s' % FLAGS.boundary_table)
      config_util.add_boundaries_to_config(pipeline_config,
                                           FLAGS.boundary_table)

    if FLAGS.sampler_table:
      pipeline_config.data_config.negative_sampler.input_path = FLAGS.sampler_table

    # parse selected_cols
    set_selected_cols(pipeline_config, FLAGS.selected_cols, FLAGS.all_cols,
                      FLAGS.all_col_types)

    distribute_strategy = DistributionStrategyMap[FLAGS.distribute_strategy]

    # update params specified by automl if hpo_param_path is specified
    if FLAGS.hpo_param_path:
      logging.info('hpo_param_path = %s' % FLAGS.hpo_param_path)
      with tf.gfile.GFile(FLAGS.hpo_param_path, 'r') as fin:
        hpo_config = json.load(fin)
        hpo_params = hpo_config['param']
        config_util.edit_config(pipeline_config, hpo_params)
    config_util.auto_expand_share_feature_configs(pipeline_config)

    print('[run.py] with_evaluator %s' % str(FLAGS.with_evaluator))
    print('[run.py] eval_method %s' % FLAGS.eval_method)
    assert FLAGS.eval_method in [
        'none', 'master', 'separate'
    ], 'invalid evalaute_method: %s' % FLAGS.eval_method
    if FLAGS.with_evaluator:
      FLAGS.eval_method = 'separate'
    num_worker = set_tf_config_and_get_train_worker_num(
        distribute_strategy=distribute_strategy, eval_method=FLAGS.eval_method)
    set_distribution_config(pipeline_config, num_worker, num_gpus_per_worker,
                            distribute_strategy)
    train_and_evaluate_impl(
        pipeline_config, continue_train=FLAGS.continue_train)

    if FLAGS.hpo_metric_save_path:
      hpo_util.save_eval_metrics(
          pipeline_config.model_dir,
          metric_save_path=FLAGS.hpo_metric_save_path,
          has_evaluator=FLAGS.with_evaluator)
  elif FLAGS.cmd == 'evaluate':
    check_param('config')
    # TODO: support multi-worker evaluation
    assert len(FLAGS.worker_hosts.split(',')) == 1, 'evaluate only need 1 woker'
    config_util.auto_expand_share_feature_configs(pipeline_config)
    pipeline_config.eval_input_path = FLAGS.tables

    distribute_strategy = DistributionStrategyMap[FLAGS.distribute_strategy]
    set_tf_config_and_get_train_worker_num(eval_method='none')
    set_distribution_config(pipeline_config, num_worker, num_gpus_per_worker,
                            distribute_strategy)

    # parse selected_cols
    set_selected_cols(pipeline_config, FLAGS.selected_cols, FLAGS.all_cols,
                      FLAGS.all_col_types)

    easy_rec.evaluate(pipeline_config, FLAGS.checkpoint_path, None,
                      FLAGS.eval_result_path)
  elif FLAGS.cmd == 'export':
    check_param('export_dir')
    check_param('config')

    redis_params = {}
    if FLAGS.redis_url:
      redis_params['redis_url'] = FLAGS.redis_url
    if FLAGS.redis_passwd:
      redis_params['redis_passwd'] = FLAGS.redis_passwd
    if FLAGS.redis_threads > 0:
      redis_params['redis_threads'] = FLAGS.redis_threads
    if FLAGS.redis_batch_size > 0:
      redis_params['redis_batch_size'] = FLAGS.redis_batch_size
    if FLAGS.redis_expire > 0:
      redis_params['redis_expire'] = FLAGS.redis_expire
    if FLAGS.redis_embedding_version:
      redis_params['redis_embedding_version'] = FLAGS.redis_embedding_version
    if FLAGS.redis_write_kv:
      redis_params['redis_write_kv'] = FLAGS.redis_write_kv

    set_tf_config_and_get_train_worker_num(eval_method='none')
    assert len(FLAGS.worker_hosts.split(',')) == 1, 'export only need 1 woker'
    config_util.auto_expand_share_feature_configs(pipeline_config)
    easy_rec.export(FLAGS.export_dir, pipeline_config, FLAGS.checkpoint_path,
                    FLAGS.asset_files, FLAGS.verbose, **redis_params)
  elif FLAGS.cmd == 'predict':
    check_param('tables')
    check_param('saved_model_dir')
    logging.info('will use the following columns as model input: %s' %
                 FLAGS.selected_cols)
    logging.info('will copy the following columns to output: %s' %
                 FLAGS.reserved_cols)

    profiling_file = FLAGS.profiling_file if FLAGS.task_index == 0 else None
    if profiling_file is not None:
      print('profiling_file = %s ' % profiling_file)
    predictor = Predictor(FLAGS.saved_model_dir, profiling_file=profiling_file)
    input_table, output_table = FLAGS.tables, FLAGS.outputs
    logging.info('input_table = %s, output_table = %s' %
                 (input_table, output_table))
    worker_num = len(FLAGS.worker_hosts.split(','))
    predictor.predict_table(
        input_table,
        output_table,
        all_cols=FLAGS.all_cols,
        all_col_types=FLAGS.all_col_types,
        selected_cols=FLAGS.selected_cols,
        reserved_cols=FLAGS.reserved_cols,
        output_cols=FLAGS.output_cols,
        batch_size=FLAGS.batch_size,
        slice_id=FLAGS.task_index,
        slice_num=worker_num)
  else:
    raise ValueError('cmd should be one of train/evaluate/export/predict')


if __name__ == '__main__':
  tf.app.run()
