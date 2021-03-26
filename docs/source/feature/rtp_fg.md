# RTP FG

### 编写配置文件 [fg.json](https://easyrec.oss-cn-beijing.aliyuncs.com/rtp_fg/fg.json)

- Feature配置说明：

  - [多值类型](http://easyrec.oss-cn-beijing.aliyuncs.com/fg_docs/%E5%A4%9A%E5%80%BC%E7%B1%BB%E5%9E%8B.pdf)

  - [IdFeature](http://easyrec.oss-cn-beijing.aliyuncs.com/fg_docs/IdFeature.pdf)

    - is\_multi: id\_feature是否是多值属性，默认是false, 转换成EasyRec的config时会转成IdFeature; 如果设成true, 转换成EasyRec的config时会转成TagFeature

  - [RawFeature](http://easyrec.oss-cn-beijing.aliyuncs.com/fg_docs/RawFeature.pdf)

  - [ComboFeature](http://easyrec.oss-cn-beijing.aliyuncs.com/fg_docs/ComboFeature.pdf)

  - [LookupFeature](http://easyrec.oss-cn-beijing.aliyuncs.com/fg_docs/LookupFeature.pdf)

    - Lookup Feature的needWeighting**没有效果**，不需要设置

  - [MatchFeature](http://easyrec.oss-cn-beijing.aliyuncs.com/fg_docs/MatchFeature.pdf)

    - Match Feature里面多值分隔符应该使用^\] (ctrl+v ctrl+\])，而不是逗号\[,\]， 如:

    ```
      50011740^107287172:0.2^]36806676:0.3^]122572685:0.5|50006842^16788816:0.1^]10122:0.2^]29889:0.3^]30068:19
    ```

  - [OverLapFeature](http://easyrec.oss-cn-beijing.aliyuncs.com/fg_docs/OverLapFeature.pdf)

  - reserves: 要在最终表里面要保存的字段，通常包括label, user\_id, item\_id等

  - separator: sparse格式里面，特征之间的分隔符，不指定默认是","，

    - 训练时，对稠密格式没有影响，对稀疏格式有影响
    - 预测时，item feature在redis里面存储的是稀疏格式，因此是有影响的

    ```
    i_item_id:10539078362,i_seller_id:21776327,...
    ```

  - multi\_val\_sep: 多值特征的分隔符，不指定默认是"\\u001D"

  ```json
  {
    "features": [
       {"expression": "user:user_id", "feature_name": "user_id", "feature_type":"id_feature", "value_type":"String", "combiner":"mean", "hash_bucket_size": 100000, "embedding_dim": 16, "group":"user"},
       {"expression": "user:cms_segid", "feature_name": "cms_segid", "feature_type":"id_feature", "value_type":"String", "combiner":"mean", "hash_bucket_size": 100, "embedding_dim": 16, "group":"user"},
       ...
       {"expression": "item:price", "feature_name": "price", "feature_type":"raw_feature", "value_type":"Integer", "combiner":"mean", "group":"item"},
       {"expression": "item:pid", "feature_name": "pid", "feature_type":"id_feature", "value_type":"String", "combiner":"mean", "hash_bucket_size": 100000, "embedding_dim": 16, "group":"item"},
       {"expression": "user:tag_category_list", "feature_name": "user_tag_cate", "feature_type":"id_feature", "hash_bucket_size":100000, "group":"user"},
       {"map": "user:tag_brand_list", "key":"item:brand", "feature_name": "combo_brand", "feature_type":"lookup_feature",  "needDiscrete":true, "hash_bucket_size":100000, "group":"combo"},
       {"map": "user:tag_category_list", "key":"item:cate_id", "feature_name": "combo_cate_id", "feature_type":"lookup_feature",  "needDiscrete":true, "hash_bucket_size":10000, "group":"combo"}
   ],
   "reserves": [
     "user_id", "campaign_id", "clk"
   ],
   "multi_val_sep": "|"
  }
  ```

### 训练

#### 2. 从fg.json生成EasyRec的config

本地安装wheel包

```bash
pip install https://easy-rec.oss-cn-hangzhou.aliyuncs.com/releases/easy_rec-0.1.0-py2.py3-none-any.whl
```

```python
python -m easy_rec.python.tools.convert_rtp_fg  --label clk --rtp_fg fg.json --model_type multi_tower --embedding_dim 10  --output_path fg.config --selected_cols "label,features"
```

- \--model\_type: 模型类型, 可选: multi\_tower, deepfm, 其它模型暂时不能设置，需要在生成的config里面增加model\_config的部分
- \--embedding\_dim: embedding dimension, 如果fg.json里面的feature没有指定embedding\_dimension, 那么将使用该选项指定的值
- \--batch\_size: batch\_size, 训练时使用的batch\_size
- \--label: label字段, 可以指定多个
- \--num\_steps: 训练的步数,默认1000
- \--output\_path: 输出的EasyRec config路径
- \--separator: feature之间的分隔符, 默认是CTRL\_B(\\u0002)
- \--selected\_cols: 指定输入列，包括label和features，其中label可以指定多列，表示要使用多个label(一般是多任务模型),  最后一列必须是features, 如:
  ```
  label0,label1,features
  ```
  - 注意不要有**空格**
- \--incol\_separator: feature内部的分隔符，即多值分隔符，默认是CTRL\_C(\\u0003)
- \--input\_type: 输入类型，默认是OdpsRTPInput, 如果在EMR上使用或者本地使用，应该用RTPInput, 如果使用RTPInput那么--selected\_cols也需要进行修改, 使用对应的列的id:
  ```
  0,4
  ```
  - 其中第0列是label, 第4列是features
  - 还需要指定--rtp\_separator，表示label和features之间的分隔符, 默认是";"
- \--train\_input\_path, 训练数据路径
  - MaxCompute上不用指定，在训练的时候指定
- \--eval\_input\_path, 评估数据路径
  - MaxCompute上不用指定，在训练的时候指定

#### 3. 上传数据(如果已经有数据，可以跳过这一步)

- 稀疏格式的数据: user特征, item特征, context特征各放一列；特征在列内以kv形式存储, 如：

| label | user\_id | item\_id | context\_feature | user\_feature                                                         | item\_feature                                         |
| ----- | -------- | -------- | ---------------- | --------------------------------------------------------------------- | ----------------------------------------------------- |
| 0     | 122017   | 389957   |                  | tag\_category\_list:4589,new\_user\_class\_level:,...,user\_id:122017 | adgroup\_id:539227,pid:430548\_1007,...,cate\_id:4281 |

```sql
-- taobao_train_input.txt oss://easyrec/data/rtp/
-- wget http://easyrec.oss-cn-beijing.aliyuncs.com/data/rtp/taobao_train_input.txt
-- wget http://easyrec.oss-cn-beijing.aliyuncs.com/data/rtp/taobao_test_input.txt
drop table if exists taobao_train_input;
create table if not exists taobao_train_input(`label` BIGINT,user_id STRING,item_id STRING,context_feature STRING,user_feature STRING,item_feature STRING);
tunnel upload taobao_train_input.txt taobao_train_input -fd=';';
drop table if exists taobao_test_input;
create table if not exists taobao_test_input(`label` BIGINT,user_id STRING,item_id STRING,context_feature STRING,user_feature STRING,item_feature STRING);
tunnel upload taobao_test_input.txt taobao_test_input -fd=';';
```

- 稠密格式的数据，每个特征是单独的一列，如：

| label | user\_id | item\_id | tag\_category\_list | new\_user\_class\_level | age\_level |
| ----- | -------- | -------- | ------------------- | ----------------------- | ---------- |
| 1     | 122017   | 389957   | 4589                |                         | 0          |

```sql
  drop table if exists taobao_train_input;
  create table taobao_train_input_dense(label bigint, user_id string, item_id string, tag_category_list bigint, ...);
```

- **Note:** 特征列名可以加上prefix: **"user\_\_", "item\_\_", "context\_\_"**

```
  如: 列名ctx_position也可以写成 context__ctx_position
```

#### 4. 生成样本

- 下载rtp\_fg [jar ](https://easy-rec.oss-cn-hangzhou.aliyuncs.com/deploy/fg_on_odps-1.3.56-jar-with-dependencies.jar)包
- 生成特征

```sql
add jar target/fg_on_odps-1.3.56-jar-with-dependencies.jar -f;
add file fg.json -f;

set odps.sql.planner.mode=sql;
set odps.isolation.session.enable=true;
set odps.sql.counters.dynamic.limit=true;

drop table if exists taobao_fg_train_out;
create table taobao_fg_train_out(label bigint, user_id string, item_id string,  features string);
jar -resources fg_on_odps-1.3.56-jar-with-dependencies.jar,fg.json -classpath fg_on_odps-1.3.56-jar-with-dependencies.jar com.taobao.fg_on_odps.EasyRecFGMapper -i taobao_train_input -o taobao_fg_train_out -f fg.json;
drop table if exists taobao_fg_test_out;
create table taobao_fg_test_out(label bigint, user_id string, item_id string,  features string);
jar -resources fg_on_odps-1.3.56-jar-with-dependencies.jar,fg.json -classpath fg_on_odps-1.3.56-jar-with-dependencies.jar com.taobao.fg_on_odps.EasyRecFGMapper -i taobao_test_input -o taobao_fg_test_out -f fg.json;

--下载查看数据(可选)
tunnel download taobao_fg_test_out taobao_fg_test_out.txt -fd=';';
```

- EasyRecFGMapper参数格式:
  - \-i, 输入表
    - 支持分区表，分区表可以指定partition，也可以不指定partition，不指定partition时使用所有partition
    - **分区格式示例:** my\_table/day=20201010,sex=male
    - 可以用多个-i指定**多个表的多个分区**
  - \-o, 输出表，如果是分区表，一定要指定分区，只能指定一个输出表
  - \-f, fg.json
  - \-m, mapper memory的大小，默认可以不设置
- EasyRecFGMapper会自动判断是**稠密格式**还是**稀疏格式**
  - 如果表里面有user\_feature和item\_feature字段，那么判定是稀疏格式
  - 否则，判定是稠密格式
- 生成的特征示例(taobao\_fg\_train\_out):

| label | user\_id | item\_id | features                                                                                                                    |
| ----- | -------- | -------- | --------------------------------------------------------------------------------------------------------------------------- |
| 0     | 336811   | 100002   | user\_id\_100002^Bcms\_segid\_5^Bcms\_group\_id\_2^Bage\_level\_2^Bpvalue\_level\_1^Bshopping\_level\_3^Boccupation\_1^B... |

#### 5. 启动训练

- 上传fg.config到oss
- 启动训练

```sql
pai -name easy_rec_ext
-Dconfig=oss://bucket-name/easy_rec_test/fg.config
-Dcmd=train
-Dtables='odps://project-name/tables/taobao_fg_train_out,odps://project-name/tables/taobao_fg_test_out'
-Dcluster='{"ps":{"count":1, "cpu":1000}, "worker" : {"count":3, "cpu":1000, "gpu":100, "memory":40000}}'
-Darn=acs:ram::xxx:role/ev-ext-test-oss
-Dbuckets=oss://bucket-name/
-DossHost=oss-cn-xxx.aliyuncs.com
-Deval_method=separate;
```

### 预测

#### 服务部署

- 使用 eascmd 来部署更新 easyrec processor 服务， easyrec processor [下载](http://easy-rec.oss-cn-hangzhou.aliyuncs.com/deploy/easyrec-eas-processor-0.0.1-jar-with-dependencies.jar)
- 部署的 service.json 示例如下

```
{
  "name":"easyrec_processor",
  "generate_token": "false",
  "model_path": "./tf_model.tar.gz",
  "processor_path": "http://easy-rec.oss-cn-hangzhou.aliyuncs.com/deploy/easyrec-eas-processor-0.0.1-jar-with-dependencies.jar",
  "processor_mainclass" :"com.alibaba.pairec.processor.EasyrecProcessor",
  "processor_type": "java",
  "model_config":"{\"redis-conf\": {\"url\":\"redis://11.158.166.161:6379/\", \"password\":\"123456\", \"prefix\":\"id_\"}, \"pool_size\": 2, \"period\": 10, \"fg_ins_num\":20}",
  "metadata": {
  	"region": "shanghai",
  	"instance": 1
  }
}
```

- model\_path:模型地址，里面包括 saved\_model.pb 和 fg.json 文件
- processor\_path， processor\_mainclass， processor\_type 自定义 easyrec processor  设置，与示例保持一致即可
- model\_config  eas 部署配置。主要控制把 item 特征加载到内存中。目前数据源只支持 redis。redis-conf 中配置了 redis 访问的相关配置，包括 url, password。 prefix 是 redis key 的前缀，一般情况下为了区分 key 的用途，会有前缀来标识。
- period: 是item feature异步加载的时间间隔。以分钟为单位，默认是 10 分钟。
- fg\_ins\_num: FG实例的数目，默认是32，一般设置的和并发数一致即可
  - 设置的过少会导致一些请求失败
    - error\_msg: feature generation instance exhausted.
    - status\_code: EXCEPTION
  - 设置的过多会消耗比较多的内存。
- eascmd 部署[参考文档](https://help.aliyun.com/document_detail/111031.html?spm=a2c4g.11186623.2.22.a55de90fNPKTLi#concept-1936147)。

#### 客户端访问

同  eas sdk 中的 TFRequest  类似，easyrec 也是试用 ProtoBuffer 作为传输协议。 proto 文件定义为：

```protobuf
syntax = "proto3";

package com.alibaba.pairec.processor;
option cc_enable_arenas = true;
option java_package = "com.alibaba.pairec.processor";
option java_outer_classname = "PredictProtos";

// context features
message ContextFeatures {
  repeated string features = 1;
}

// PBRequest specifies the request for aggregator
message PBRequest {
  // debug mode
  bool debug_mode = 1;

  // user features
  map<string, string> user_features = 2;

  // item ids
  repeated string item_ids = 3;

  // context features for each item
  map<string, ContextFeatures> context_features = 4;
}

// return results
message Results {
  repeated double scores = 1 [packed = true];
}

enum StatusCode {
  OK = 0;
  INPUT_EMPTY = 1;
  EXCEPTION = 2;
}

// PBResponse specifies the response for aggregator
message PBResponse {
  // results
  map<string, Results> results = 1;

  // item features
  map<string, string> item_features = 2;

  // generate features
  map<string, string> generate_features = 3;

  // context features
  map<string, ContextFeatures> context_features = 4;

  string error_msg = 5;

  StatusCode status_code = 6;
}
```

提供了 java 的客户端实例，[客户端 jar 包地址](http://easy-rec.oss-cn-hangzhou.aliyuncs.com/deploy/easyrec-eas-client-0.0.1-jar-with-dependencies.jar)。
下载后的 jar 通过下面命令安装到本地 mvn 库里。

```
mvn install:install-file -Dfile=easyrec-eas-client-0.0.1-jar-with-dependencies.jar -DgroupId=com.alibaba.pairec -DartifactId=easyrec-eas-client -Dversion=0.0.1 -Dpackaging=jar
```

然后通过

```
<dependency>
    <groupId>com.alibaba.pairec</groupId>
    <artifactId>easyrec-eas-client</artifactId>
    <version>0.0.1</version>
</dependency>
```

java 客户端测试代码参考：

```java
public class PredictClient {
    @Test
    public void easyrecPredictClient() {
        PaiPredictClient client = new PaiPredictClient(new HttpConfig());
        client.setEndpoint("localhost:5749");
        client.setModelName("easyrec_processor");

        String sampleFile = PredictClient.class.getResource("/all_sample.txt").getPath();
        File file = new File(sampleFile);
        BufferedReader reader = null;
        try {
            reader = new BufferedReader(new FileReader(file));
            String tempStr;
            while ((tempStr = reader.readLine()) != null) {
                predictSampleString(tempStr, client);
            }
            reader.close();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void predictSampleString(String sampleStr, PaiPredictClient client) throws Exception {
        String[] strLists = sampleStr.split(";");
        EasyrecRequest easyrecRequest = new EasyrecRequest();
        // Parse user features
        String userFeatures = strLists[4];
        easyrecRequest.appendUserFeatureString(userFeatures);
        // Parse context features
        String contextFeatures = strLists[3];
        easyrecRequest.appendContextFeatureString(contextFeatures);
        // Parse item features
        String itemIdStr = strLists[2];
        easyrecRequest.appendItemStr(itemIdStr);
        PredictProtos.PBResponse response = client.predict(easyrecRequest);
        if (null == response) {
            throw new RuntimeException("response is null");
        }
        for (Map.Entry<String, PredictProtos.Results> entry : response.getResultsMap().entrySet()) {
            String key = entry.getKey();
            PredictProtos.Results value = entry.getValue();
            System.out.print("key: " + key);
            for (int i = 0; i < value.getScoresCount(); i++) {
                System.out.format(" value: %.4f ", value.getScores(i));
            }
            System.out.println();
        }
    }
}

```
