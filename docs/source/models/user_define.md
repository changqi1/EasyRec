# 自定义模型

### 获取EasyRec源码

```bash
git clone git@gitlab.alibaba-inc.com:pai_biz_arch/easy-rec.git
git submodule init
git submodule update
python git-lfs/git_lfs.py pull
# 运行测试用例确保通过
python -m easy_rec.python.test.run
sh scripts/end2end_test.sh
```

### 编写模型proto文件

```protobuf
# easy_rec/python/protos/custom_model.proto
syntax="proto2";
package protos;
import "easy_rec/python/protos/dnn.proto";

message CustomModel {
  required DNN dnn = 1;

  ...

  required float dense_regularization = 6 [default=1e-4];
};
```

#### 修改easy\_rec\_model.proto:

easy\_rec/python/protos/easy\_rec\_model.proto:

- import custom\_model.proto
- 在oneof model里面增加CustomModel

```protobuf
syntax="proto2";
package protos;

import "easy_rec/python/protos/deepfm.proto";
...
import "easy_rec/python/protos/custom_model.proto"

...

message EasyRecModel {
   required string model_class = 1;

   // actually input layers, each layer produce a group of feature
   repeated FeatureGroupConfig feature_groups = 2;

   // model parameters
   oneof model {
      DummyModel dummy = 3;
      WideAndDeep wide_and_deep = 4;
      DeepFM deepfm = 5;
      MultiTower multi_tower = 6;
      CustomModel custom_model = 7;
      ...
```

#### proto编译

```protobuf
sh scripts/gen_proto.sh
```

### 编写模型文件

#### 继承

- 一般都继承自EasyRecModel，在调用super(CustomModel, self).\_\_init\_\_的过程中会构建以下对象，因此子类中不需要再构建下面的对象

```
  self._base_model_config = model_config
  # will be override by subclass
  self._model_config = model_config
  self._is_training = is_training
  self._feature_dict = features
  self._feature_configs = feature_configs
  self._emb_reg = regularizers.l2_regularizer(self.embedding_regularization)
  self._labels = labels

  # will be filled by build_predict_graph function, which is implemented in subclass
  # and will be used by EasyRec framework
  self._prediction_dict = {}

  # will be filled by build_loss_graph function, which is implemented in subclass
  # and will used by EasyRec framework for calculating gradients, and do back propagation.
  self._loss_dict = {}
```

- 如果是Rank模型，则推荐继承自RankModel
  - 可以复用RankModel的build\_predict\_graph和build\_loss\_graph
  - 可以利用RankModel中实现的\_add\_to\_prediction\_dict把build\_predict\_graph中DNN的输出加入到self.\_prediction\_dict中，具体参考DeepFM和MultiTower的实现。

#### 初始化函数: __init__(self, model\_config, feature\_configs, features, labels, is\_training)

- model\_config: 模型配置, easy\_rec.python.protos.easy\_rec\_model\_pb2.EasyRecModel对象
  - model\_config.custom\_model: easy\_rec.python.protos.custom\_model\_pb2.CustomModel对象，是模型特有的参数
  - model\_config.feature\_groups: 特征组，如DeepFM包含deep组和wide组，多塔算法包含user组、item组、combo组等
- feature\_configs: feature column配置，使用self.\_input\_layer可以获得经过feature\_column处理过的特征
- features: 原始输入
- labels: 样本的label
- is\_training: 是否是训练，其它状态(评估/预测)。

#### 前向函数: build\_predict\_graph

- 使用输入的features，使用tensorflow的函数构建深度模型，输出预测值y，预测值y放到self.\_prediction\_dict中
- Return: self.\_prediction\_dict

#### 损失函数: build\_loss\_graph

- 使用build\_predict\_graph函数中输出的预测值y和self.\_labels构建损失函数，loss tensor加入到self.\_loss\_dict
- self.\_labels通常是一个tensor list，如果CustomModel继承自RankModel，那么self.\_labels是一个tensor
- Return: self.\_loss\_dict
- loss会被EasyRec框架记录(tf.summary), 写入model\_dir目录下的events.\*文件

#### 评估函数: build\_metric\_graph(self, eval\_config)

- eval\_config: easy\_rec.python.protos.eval\_pb2.EvalConfig:
  - 一般根据其中的metric\_sets来确定要计算哪些metric
- 使用build\_predict\_graph函数中输出的预测值y和self.\_labels构建metric op
- Return: dict of {"metric\_name" : metric\_tensor }
- metric会被EasyRec框架记录(tf.summary), 写入model\_dir目录下的events.\*文件

```python
# easy_rec/python/model/custom_model.py
import os
import sys
import six
import tensorflow as tf

if tf.__version__ >= "2.0":
    tf = tf.compat.v1

from easy_rec.python.model.easy_rec_model import EasyRecModel
from easy_rec.python.feature_column.feature_column import FeatureColumnParser
from easy_rec.python.protos.deepfm_pb2 import DeepFM as DeepFMConfig
from easy_rec.python.compat import regularizers
from easy_rec.python.protos.easy_rec_model_pb2 import LossType


class CustomModel(EasyRecModel):
    def __init__(
        self, model_config, feature_configs, features, labels=None, is_training=False
    ):
        """
        Args:
          model_config: easy_rec.python.protos.easy_rec_model_pb2.EasyRecModel
               model_config.custom_model is instance of:
                     easy_rec.python.protos.easy_rec_model_pb2.CustomModel
          feature_configs: a collection of easy_rec.python.protos.feature_config.FeatureConfig
          features: dict of feature tensors, which are described by easy_rec.python.protos.DatasetConfig.input_fields
          labels: dict of labels tensors, which are described by easy_rec.python.protos.DatasetConfig.label_fields
        """
        super(CustomModel, self).__init__(
            model_config, feature_configs, features, labels, is_training
        )
        """
       use feature columns to build complex features from features(input)
       use self._input_layer to build features from feature_configs:
    """
        self._wide_features, _ = self._input_layer(self._feature_dict, "wide")
        """
      self._deep_features are a single tensor, where the all features are concatentated into one,
      self._deep_feature_list is a list of tensors, each feature_config lead to one tensor.
    """
        self._deep_features, self._deep_feature_lst = self._input_layer(
            self._feature_dict, "deep"
        )
        self._user_features, self._user_feature_lst = self._input_layer(
            self._feature_dict, "user"
        )
        self._item_features, self._item_feature_lst = self._input_layer(
            self._feature_dict, "item"
        )
        """
      The deep, user, item corresponds to feature_groups defined in model_config.feature_groups:
        "deep", "user", "item" are the feature_group names.
      It is suggested to use the feature_configs to build features.
      But if the feature_configs could not satified your requirements, you can use tensorflow
      functions to process the raw inputs in features.
      ...
    """

        # do some other initializing work
        ...

    def build_predict_graph(self):
        # build forward graph
        ...
        self._prediction_dict["y"] = y
        # it is necessary to return the prediction_dict, which is required by EasyRecEstimator
        return self._prediction_dict

    def build_loss_graph(self):
        assert self._model_config.loss_type == LossType.CLASSIFICATION
        loss = ...
        self._loss_dict["custom_loss"] = loss
        return self._loss_dict

    def build_metric_graph(self, eval_config):
        metric_dict = {}
        for metric in eval_config.metrics_set:
            if metric.WhichOneof("metric") == "auc":
                metric_dict["auc"] = tf.metrics.auc(
                    self._labels[0], self._prediction_dict["y"]
                )
            else:
                ...
        return metric_dict
```

#### Note:

如果是RankModel则直接继承easy\_rec.python.model.rank\_model.RankModel，可以省略:

- build\_loss\_graph
- build\_metric\_graph

因为这两个函数在RankModel里面已经完成了

### 测试

#### 编写pipeline.config

```protobuf
# 训练表和测试表，如果在PAI上，会被-Dtables参数覆盖
train_input_path: "train_longonehot_4deepfm_20.csv"
eval_input_path: "test_longonehot_4deepfm_20.csv"
# 模型保存路径
model_dir: "experiment/custom_model_ctr/"

# 数据相关的描述
data_config {
  ...
}

# 特征相关
feature_configs : {
  ...
}
feature_configs : {
  ...
}

# 训练相关的参数
train_config {
  ...
}

# 评估相关
eval_config {
  ...
}

# 模型相关
model_config: {
  model_class: 'CustomModel'
  feature_groups: {
    group_name: 'wide'
    feature_names: 'field[1-20]'
    wide_deep: WIDE
  }
  feature_groups: {
    group_name: 'deep'
    feature_names: 'field[1-20]'
    wide_deep: DEEP
  }
  # you can define any groups, and use it in your model
  feature_groups: {
    group_name: 'user'
    feature_names: 'field[5-10]'
    wide_deep: DEEP
  }
  ...

  custom_model {
    # specify the params defined in easy_rec/python/protos/custom_model.proto
    ...
  }

  embedding_regularization: 1e-5
}
```

#### 增加测试数据到data/test/

#### 增加测试用例到scripts/end2end\_test.sh

```bash
python -m easy_rec.python.train_eval --pipeline_config_path pipeline.config
```

运行测试用例

```bash
scripts/end2end_test.sh
```

确保所有用例都通过了

#### 提交代码

```shell
python git-lfs/git_lfs.py add data/test/your_data_files
python git-lfs/git_lfs.py push
git add your_config_file your_code.py
git commit -a -m "add new model xxx"
git push origin your_branch
```