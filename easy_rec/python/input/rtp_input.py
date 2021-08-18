# -*- encoding:utf-8 -*-
# Copyright (c) Alibaba, Inc. and its affiliates.
import logging

import numpy as np
import tensorflow as tf

from easy_rec.python.input.input import Input

if tf.__version__ >= '2.0':
  tf = tf.compat.v1


class RTPInput(Input):
  """RTPInput for parsing rtp fg new input format.

  Our new format(csv in csv) of rtp output:
     label0, item_id, ..., user_id, features
  here the separator(,) could be specified by data_config.rtp_separator
  For the feature column, features are separated by ,
     multiple values of one feature are separated by , such as:
     ...20beautysmartParis...
  The features column and labels are specified by data_config.selected_cols,
     columns are selected by indices as our csv file has no header,
     such as: 0,1,4, means the 4th column is features, the 1st and 2nd
     columns are labels
  """

  def __init__(self,
               data_config,
               feature_config,
               input_path,
               task_index=0,
               task_num=1):
    super(RTPInput, self).__init__(data_config, feature_config, input_path,
                                   task_index, task_num)
    logging.info('input_fields: %s label_fields: %s' %
                 (','.join(self._input_fields), ','.join(self._label_fields)))
    self._rtp_separator = self._data_config.rtp_separator
    if not isinstance(self._rtp_separator, str):
      self._rtp_separator = self._rtp_separator.encode('utf-8')
    self._selected_cols = [
        int(x) for x in self._data_config.selected_cols.split(',')
    ]
    self._num_cols = -1
    self._feature_col_id = self._selected_cols[-1]
    logging.info('rtp separator = %s' % self._rtp_separator)

  def _parse_csv(self, line):
    record_defaults = ['' for i in range(self._num_cols)]
    lbl_id = 0
    for x, t, v in zip(self._input_fields, self._input_field_types,
                       self._input_field_defaults):
      if x not in self._label_fields:
        continue
      record_defaults[self._selected_cols[lbl_id]] = self.get_type_defaults(
          t, v)

    # the actual features are in one single column
    record_defaults[self._feature_col_id] = self._data_config.separator.join([
        str(self.get_type_defaults(t, v))
        for x, t, v in zip(self._input_fields, self._input_field_types,
                           self._input_field_defaults)
        if x not in self._label_fields
    ])

    fields = tf.string_split(line, self._rtp_separator, skip_empty=False)
    fields = tf.reshape(fields.values, [-1, len(record_defaults)])
    labels = [fields[:, x] for x in self._selected_cols[:-1]]

    # only for features, labels excluded
    record_defaults = [
        self.get_type_defaults(t, v)
        for x, t, v in zip(self._input_fields, self._input_field_types,
                           self._input_field_defaults)
        if x not in self._label_fields
    ]
    # assume that the last field is the generated feature column
    print('field_delim = %s' % self._data_config.separator)
    fields = tf.string_split(
        fields[:, self._feature_col_id],
        self._data_config.separator,
        skip_empty=False)
    tmp_fields = tf.reshape(fields.values, [-1, len(record_defaults)])
    fields = []
    for i in range(len(record_defaults)):
      if type(record_defaults[i]) == int:
        fields.append(
            tf.string_to_number(
                tmp_fields[:, i], tf.int64, name='field_as_int_%d' % i))
      elif type(record_defaults[i]) in [float, np.float32, np.float64]:
        fields.append(
            tf.string_to_number(
                tmp_fields[:, i], tf.float32, name='field_as_flt_%d' % i))
      elif type(record_defaults[i]) in [str, type(u''), bytes]:
        fields.append(tmp_fields[:, i])
      elif type(record_defaults[i]) == bool:
        fields.append(
            tf.logical_or(
                tf.equal(tmp_fields[:, i], 'True'),
                tf.equal(tmp_fields[:, i], 'true')))
      else:
        assert 'invalid types: %s' % str(type(record_defaults[i]))

    field_keys = [x for x in self._input_fields if x not in self._label_fields]
    effective_fids = [field_keys.index(x) for x in self._effective_fields]
    inputs = {field_keys[x]: fields[x] for x in effective_fids}

    for x in range(len(self._label_fields)):
      inputs[self._label_fields[x]] = labels[x]
    return inputs

  def _build(self, mode, params):
    file_paths = tf.gfile.Glob(self._input_path)
    assert len(file_paths) > 0, 'match no files with %s' % self._input_path

    # try to figure out number of fields from one file
    with tf.gfile.GFile(file_paths[0], 'r') as fin:
      num_lines = 0
      for line_str in fin:
        line_tok = line_str.strip().split(self._rtp_separator)
        if self._num_cols != -1:
          assert self._num_cols == len(line_tok)
        self._num_cols = len(line_tok)
        num_lines += 1
        if num_lines > 10:
          break
    logging.info('num selected cols = %d' % self._num_cols)

    record_defaults = [
        self.get_type_defaults(t, v)
        for x, t, v in zip(self._input_fields, self._input_field_types,
                           self._input_field_defaults)
        if x in self._label_fields
    ]

    # the features are in one single column
    record_defaults.append(
        self._data_config.separator.join([
            str(self.get_type_defaults(t, v))
            for x, t, v in zip(self._input_fields, self._input_field_types,
                               self._input_field_defaults)
            if x not in self._label_fields
        ]))

    num_parallel_calls = self._data_config.num_parallel_calls
    if mode == tf.estimator.ModeKeys.TRAIN:
      logging.info('train files[%d]: %s' %
                   (len(file_paths), ','.join(file_paths)))
      dataset = tf.data.Dataset.from_tensor_slices(file_paths)
      if self._data_config.shuffle:
        # shuffle input files
        dataset = dataset.shuffle(len(file_paths))
      # too many readers read the same file will cause performance issues
      # as the same data will be read multiple times
      parallel_num = min(num_parallel_calls, len(file_paths))
      dataset = dataset.interleave(
          tf.data.TextLineDataset,
          cycle_length=parallel_num,
          num_parallel_calls=parallel_num)
      if self._data_config.chief_redundant:
        dataset = dataset.shard(
            max(self._task_num - 1, 1), max(self._task_index - 1, 0))
      else:
        dataset = dataset.shard(self._task_num, self._task_index)
      if self._data_config.shuffle:
        dataset = dataset.shuffle(
            self._data_config.shuffle_buffer_size,
            seed=2020,
            reshuffle_each_iteration=True)
      dataset = dataset.repeat(self.num_epochs)
    else:
      logging.info('eval files[%d]: %s' %
                   (len(file_paths), ','.join(file_paths)))
      dataset = tf.data.TextLineDataset(file_paths)
      dataset = dataset.repeat(1)

    dataset = dataset.batch(batch_size=self._data_config.batch_size)

    dataset = dataset.map(
        self._parse_csv,
        num_parallel_calls=self._data_config.num_parallel_calls)

    # preprocess is necessary to transform data
    # so that they could be feed into FeatureColumns
    dataset = dataset.map(
        map_func=self._preprocess,
        num_parallel_calls=self._data_config.num_parallel_calls)

    dataset = dataset.prefetch(buffer_size=self._prefetch_size)

    if mode != tf.estimator.ModeKeys.PREDICT:
      dataset = dataset.map(lambda x:
                            (self._get_features(x), self._get_labels(x)))
    else:
      dataset = dataset.map(lambda x: (self._get_features(x)))
    return dataset
