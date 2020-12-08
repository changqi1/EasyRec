# -*- encoding:utf-8 -*-
# Copyright (c) Alibaba, Inc. and its affiliates.

import argparse
import logging
import shutil
import sys

import tensorflow as tf

from easy_rec.python.test.odps_test import OdpsTest
from easy_rec.python.test.odps_test_prepare import prepare
from easy_rec.python.test.odps_test_util import OdpsOSSConfig
from easy_rec.python.test.odps_test_util import delete_oss_path
from easy_rec.python.test.odps_test_util import get_oss_bucket

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s][%(levelname)s] %(message)s')

odps_oss_config = OdpsOSSConfig()


class TestPipelineOnOdps(tf.test.TestCase):
  """train eval export test on odps."""

  def test_deepfm(self):
    start_files = [
        'deep_fm/create_external_deepfm_table.sql',
        'deep_fm/create_inner_deepfm_table.sql'
    ]
    test_files = [
        'deep_fm/train_deepfm_model.sql', 'deep_fm/eval_deepfm.sql',
        'deep_fm/export_deepfm.sql', 'deep_fm/predict_deepfm.sql'
    ]
    end_file = ['deep_fm/drop_table.sql']

    tot = OdpsTest(start_files, test_files, end_file, odps_oss_config)
    tot.start_test()
    tot.drop_table()

  def test_mmoe(self):
    start_files = [
        'mmoe/create_external_mmoe_table.sql',
        'mmoe/create_inner_mmoe_table.sql'
    ]
    test_files = [
        'mmoe/train_mmoe_model.sql',
        'mmoe/eval_mmoe.sql',
        'mmoe/export_mmoe.sql',
        'mmoe/predict_mmoe.sql',
    ]
    end_file = ['mmoe/drop_mmoe_table.sql']
    tot = OdpsTest(start_files, test_files, end_file, odps_oss_config)
    tot.start_test()
    tot.drop_table()

  def test_dssm(self):
    start_files = [
        'dssm/create_external_dssm_table.sql',
        'dssm/create_inner_dssm_table.sql',
    ]
    test_files = [
        'dssm/train_dssm_model.sql',
        'dssm/eval_dssm.sql',
        'dssm/export_dssm.sql',
        'dssm/predict_dssm.sql',
    ]
    end_file = [
        'dssm/drop_dssm_table.sql',
    ]
    tot = OdpsTest(start_files, test_files, end_file, odps_oss_config)
    tot.start_test()
    tot.drop_table()

  def test_multi_tower(self):
    start_files = [
        'multi_tower/create_external_multi_tower_table.sql',
        'multi_tower/create_inner_multil_tower_table.sql',
    ]
    test_files = [
        'multi_tower/train_multil_tower_din_model.sql',
        'multi_tower/train_multil_tower_bst_model.sql',
        'multi_tower/eval_multil_tower.sql',
        'multi_tower/export_multil_tower.sql',
        'multi_tower/predict_multil_tower.sql',
    ]
    end_file = ['multi_tower/drop_multil_tower_table.sql']
    tot = OdpsTest(start_files, test_files, end_file, odps_oss_config)
    tot.start_test()
    tot.drop_table()

  def test_other(self):
    start_files = [
        'deep_fm/create_external_deepfm_table.sql',
        'deep_fm/create_inner_deepfm_table.sql'
    ]
    test_files = [
        # 'other_test/test_train_gpuRequired_mirrored', # 线上报错，
        # 'other_test/test_train_distribute_strategy_collective',  # 线上报错，
        'other_test/test_train_hpo_with_evaluator.sql',
        'other_test/test_train_version.sql',
        'other_test/test_train_distribute_strategy_ess.sql',
        'other_test/test_eval_checkpoint_path.sql',
        'other_test/test_export_checkpoint_path.sql',
        'other_test/test_predict_selected_cols.sql',
    ]
    end_file = ['other_test/drop_table.sql']
    tot = OdpsTest(start_files, test_files, end_file, odps_oss_config)
    tot.start_test()
    tot.drop_table()

  def test_embedding_variable(self):
    start_files = [
        'embedding_variable/create_table.sql',
    ]
    test_files = [
        'embedding_variable/train.sql', 'embedding_variable/export.sql'
    ]
    end_file = ['embedding_variable/drop_table.sql']
    tot = OdpsTest(start_files, test_files, end_file, odps_oss_config)
    tot.start_test()
    tot.drop_table()


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--odps_config', type=str, default=None, help='odps config path')
  parser.add_argument(
      '--oss_config', type=str, default=None, help='ossutilconfig path')
  parser.add_argument(
      '--bucket_name', type=str, default=None, help='test oss bucket name')
  parser.add_argument('--arn', type=str, default=None, help='oss rolearn')
  parser.add_argument(
      '--odpscmd', type=str, default='odpscmd', help='odpscmd path')
  parser.add_argument(
      '--algo_project', type=str, default=None, help='algo project name')
  parser.add_argument(
      '--algo_res_project',
      type=str,
      default=None,
      help='algo resource project name')
  parser.add_argument(
      '--algo_version', type=str, default=None, help='algo version')
  args, unknown_args = parser.parse_known_args()
  sys.argv = [sys.argv[0]]
  for unk_arg in unknown_args:
    sys.argv.append(unk_arg)

  if args.odps_config:
    odps_oss_config.load_odps_config(args.odps_config)
  if args.oss_config:
    odps_oss_config.load_oss_config(args.oss_config)
  if args.odpscmd:
    odps_oss_config.odpscmd_path = args.odpscmd
  if args.algo_project:
    odps_oss_config.algo_project = args.algo_project
  if args.algo_res_project:
    odps_oss_config.algo_res_project = args.algo_res_project
  if args.algo_version:
    odps_oss_config.algo_version = args.algo_version
  if args.arn:
    odps_oss_config.arn = args.arn
  if args.bucket_name:
    odps_oss_config.bucket_name = args.bucket_name

  prepare(odps_oss_config)
  tf.test.main()
  bucket = get_oss_bucket(odps_oss_config.oss_key, odps_oss_config.oss_secret,
                          odps_oss_config.endpoint, odps_oss_config.bucket_name)
  delete_oss_path(bucket, odps_oss_config.exp_dir, odps_oss_config.bucket_name)
  shutil.rmtree(odps_oss_config.temp_dir)