# AMSG
Automatic Malware Signature Generation Tool.

# Description

# Requirements

The tool exploits <a href='https://mlflow.org/' title='mlflow'>mlflow</a> open source platform ot package the code in a reusable and reproducible way, to manage the running environment and log results.
Moreover, the project environment is based on a <a href='https://docs.conda.io/en/latest/' title='Conda'>Conda</a> environment.

Therefore, to run this code, it is necessary to have installed both <a href='https://mlflow.org/' title='mlflow'>mlflow</a> and <a href='https://docs.conda.io/en/latest/' title='Conda'>Conda</a>:
- To install <a href='https://mlflow.org/' title='mlflow'>mlflow</a> you can use: `pip install -q mlflow`.
- To install <a href='https://docs.conda.io/en/latest/' title='Conda'>Conda</a>, please refer to https://www.anaconda.com/products/individual or https://docs.conda.io/en/latest/miniconda.html

Further necessary packages will be downloaded automatically.

# How to Run - Workflows

## Config file
The file `config.ini` contains the base configuration elements the user can tweak to change the tool workflow.

In particular this file contains the following elements:
1. Section `sorel20mDataset`
   - `training_n_samples`: max number of training data samples to use (if -1 -> takes all)
   - `validation_n_samples`: max number of validation data samples to use (if -1 -> takes all)
   - `test_n_samples`: max number of test data samples to use (if -1 -> takes all)
   - `validation_test_split`: (should not be changed) timestamp that divides the validation data (used to check convergence/overfitting) from test data (used to assess final performance)
   - `train_validation_split`: (should not be changed) timestamp that splits training data from validation data
   - `total_training_samples`: (should not be changed) total number of available training samples in the original Sorel20M dataset
   - `total_validation_samples`: (should not be changed) total number of available validation samples in the original Sorel20M dataset
   - `total_test_samples`: (should not be changed) total number of available test samples in the original Sorel20M dataset
1. Section `detectionBase`
   - `device`: desired device to train the model on, e.g. 'cuda:0' if a GPU is available, otherwise 'cpu'
   - `workers`: number of workers to be used (if 0 -> set to current system cpu count)
   - `runs`: number of training runs to do
   - `batch_size`: how many samples per batch to load
   - `epochs`: how many epochs to train for
   - `use_malicious_labels`: whether or not (1/0) to use malware/benignware labels as a target
   - `use_count_labels`: whether or not (1/0) to use the counts as an additional target
   - `use_tag_labels`: whether or not (1/0) to use the tags as additional targets
   - `layer_sizes`: define detectionBase net initial linear layers sizes (and amount). Examples:
      - `[512,512,128]`: the initial layers (before the task branches) will be 3 with sizes 512, 512, 128 respectively
      - `[512,256]`: the initial layers (before the task branches) will be 2 with sizes 512, 256 respectively
   - `dropout_p`: dropout probability between the first detectionBase net layers
   - `activation_function`: activation function between the first detectionBase net layers. Possible values:
      - `elu`: Exponential Linear Unit activation function
      - `leakyRelu`: leaky Relu activation function
      - `pRelu`: parametric Relu activation function (better to use this with weight decay = 0)
      - `relu`: Rectified Linear Unit activation function
   - `loss_weights`: label weights to be used during loss calculation (Notice: only the weights corresponding to enabled labels will be used). Example: `{'malware': 1.0, 'count': 0.1, 'tags': 1.0}`
   - `optimizer`: optimizer to use during training. Possible values:
      - `adam`: Adam algorithm
      - `sgd`: stochastic gradient descent
   - `lr`: learning rate to use during training
   - `momentum`: momentum to be used during training when using 'sgd' optimizer
   - `weight_decay`: weight decay (L2 penalty) to use with selected optimizer
   - `gen_type`: generator type. Possible values are:
      - `base`: use basic generator (from the original SOREL20M code) modified to work with the pre-processed dataset
      - `alt1`: use alternative generator 1. Inspired by the 'index select' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
      - `alt2`: use alternative generator 2. Inspired by the 'shuffle in-place' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
      - `alt3`: use alternative generator 3. This version uses a new dataloader class, called FastTensorDataloader which asynchronously (if workers > 1) loads the dataset into memory in randomly chosen chunks which are concatenated together to form a 'chunk aggregate' -> the data inside a chunk aggregate is then shuffled. Finally batches of data are extracted from a chunk aggregate. The samples shuffling is therefore more localised but the loading speed is greatly increased
1. Section `jointEmbedding`
   - `device`: desired device to train the model on, e.g. 'cuda:0' if a GPU is available, otherwise 'cpu'
   - `workers`: number of workers to be used (if 0 -> set to current system cpu count)
   - `runs`: number of training runs to do
   - `batch_size`: how many samples per batch to load
   - `epochs`: how many epochs to train for
   - `use_malicious_labels`: whether or not (1/0) to use malware/benignware labels as a target
   - `use_count_labels`: whether or not (1/0) to use the counts as an additional target
   - `layer_sizes`: define JointEmbedding net initial linear layers sizes (and amount). Examples:
      - `[512,512,128]`: the initial layers (before the task branches) will be 3 with sizes 512, 512, 128 respectively
      - `[512,256]`: the initial layers (before the task branches) will be 2 with sizes 512, 256 respectively
   - `dropout_p`: dropout probability between the first JointEmbedding net layers
   - `activation_function`: activation function between the first detectionBase net layers. Possible values:
      - `elu`: Exponential Linear Unit activation function
      - `leakyRelu`: leaky Relu activation function
      - `pRelu`: parametric Relu activation function (better to use this with weight decay = 0)
      - `relu`: Rectified Linear Unit activation function
   - `loss_weights`: label weights to be used during loss calculation (Notice: only the weights corresponding to enabled labels will be used). Example: `{'malware': 1.0, 'count': 0.1, 'tags': 1.0}`
   - `optimizer`: optimizer to use during training. Possible values:
      - `adam`: Adam algorithm
      - `sgd`: stochastic gradient descent
   - `lr`: learning rate to use during training
   - `momentum`: momentum to be used during training when using 'sgd' optimizer
   - `weight_decay`: weight decay (L2 penalty) to use with selected optimizer
   - `gen_type`: generator type. Possible values are:
       - `base`: use basic generator (from the original SOREL20M code) modified to work with the pre-processed dataset
       - `alt1`: use alternative generator 1. Inspired by the 'index select' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
       - `alt2`: use alternative generator 2. Inspired by the 'shuffle in-place' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
       - `alt3`: use alternative generator 3. This version uses a new dataloader class, called FastTensorDataloader which asynchronously (if workers > 1) loads the dataset into memory in randomly chosen chunks which are concatenated together to form a 'chunk aggregate' -> the data inside a chunk aggregate is then shuffled. Finally batches of data are extracted from a chunk aggregate. The samples shuffling is therefore more localised but the loading speed is greatly increased
   - `similarity_measure`: similarity measure used to evaluate distances in joint embedding space. Possible values are:
      - `dot`: dot product between vectors in the embedding space. The similarity measure used in JointEmbedding paper
      - `cosine`: cosine similarity between vectors in the embedding space
      - `pairwise_distance`: calculates the pairwise distance and then transforms it to a similarity measure (between 0 and 1)
   - `pairwise_distance_to_similarity_function`: (IF 'pairwise_distance' IS SELECTED AS similarity_measure) - distance-to-similarity function to use. These functions will map values belonging to the R+ set (Real positives) to real values belonging to the [0,1] interval. Possible values are:
      - `exp`: will compute e^(-x/a)
      - `inv`: will compute 1/(1+x/a)
      - `inv_pow`: will compute 1/(1+(x^2)/a)
   
      where 'a' is a multiplicative factor (see 'pairwise_a')
   - `pairwise_a`: (IF 'pairwise_distance' IS SELECTED AS similarity_measure) - distance-to-similarity function 'a' multiplicative factor

1. Section `freshDataset`:
   - `signatures`: malware Bazaar families of interest. NOTE: It is recommended to specify more families than 'number_of_families' since Malware Bazaar may not have 'amount_each' samples for some of them. These families will be considered in order.
   - `number_of_families`: number of families to consider. The ones in excess, going in order, will not be considered.
   - `amount_each`: amount of samples for each malware family to retrieve from Malware Bazaar
   - `queries`: number of queries to do in model (fresh) evaluation

## Joint Embedding Workflow (main)

Command used to activate an entire Automatic Malware Signature Generation MLflow workflow using values set in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>.
In particular the workflow is composed of the following steps:
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#dataset-download' title='Dataset Download'>Dataset Download</a> (if both the pre-processed and the original SOREL20M dataset are not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#pre-process-dataset' title='Pre-Process Dataset'>Pre-Process Dataset</a> (if the pre-processed dataset is not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#build-fresh-dataset' title='Build Fresh Dataset'>Build Fresh Dataset</a> (if the fresh dataset is not present on disk)
1. For 'runs' (configurable in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>) times:
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#train-network' title='Train Network'>Train Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-network' title='Evaluate Network'>Evaluate Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-all-run-results' title='Compute All Run Results'>Compute All Run Results</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-fresh' title='Evaluate Fresh'>Evaluate Fresh</a>
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-all-roc-distributions' title='Plot All ROC Distributions'>Plot All ROC Distributions</a>
    
```
mlflow run /path/to/Automatic-Malware-Signature-Generation \
-P base_dir=<tool destination dir> \
-P use_cache=<whether to skip already executed runs (in cache) or not (1/0). (default: 1)> \
-P ignore_git=<whether to ignore git version or not (1/0)(default: 0)>
```

---
## Base Detection Workflow

Command used to activate an entire Base detection MLflow workflow using values set in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>.
In particular the workflow is composed of the following steps:
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#dataset-download' title='Dataset Download'>Dataset Download</a> (if both the pre-processed and the original SOREL20M dataset are not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#pre-process-dataset' title='Pre-Process Dataset'>Pre-Process Dataset</a> (if the pre-processed dataset is not present on disk)
1. For 'runs' (configurable in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>) times:
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#train-network' title='Train Network'>Train Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-network' title='Evaluate Network'>Evaluate Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-all-run-results' title='Compute All Run Results'>Compute All Run Results</a>
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-all-roc-distributions' title='Plot All ROC Distributions'>Plot All ROC Distributions</a>
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e detection_workflow \
-P base_dir=<tool destination dir> \
-P use_cache=<whether to skip already executed runs (in cache) or not (1/0) (default: 1)> \
-P ignore_git=<whether to ignore git version or not (1/0) (default: 0)>
```

---
# How to Run - Single steps
## Dataset Download

Command used to download SOREL20M dataset elements from the s3 socket and save them in the specified destination directory on the current machine.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e download_dataset \
-P destination_dir=<path to the destination folder where to save the element to>
```

---
## Pre-process Dataset
### Pre-process Dataset

Command used to pre-process SOREL20M dataset transforming it to a more easy (and quick) to read dataset format.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e preprocess_dataset \
-P ds_path=<path to the directory containing the meta.db file> \
-P destination_dir=<the directory where to save the pre-processed dataset files> \
-P training_n_samples=<max number of training data samples to use (if -1 -> takes all) (default: -1)> \
-P validation_n_samples=<max number of validation data samples to use (if -1 -> takes all) (default: -1)> \
-P test_n_samples=<max number of test data samples to use (if -1 -> takes all) (default: -1)> \
-P batch_size=<how many samples per batch to load (default: 8192)> \
-P remove_missing_features=<Strategy for removing missing samples, with meta.db entries but no associated features, from the data>
```

Note on remove_missing_features: it can be False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the database
in order to remove the data points with missing features; in case it is a filepath then a file (in Json format) will be used to
determine the data points with missing features.

### Alternative

If the current machine/instance disk capacity is not enough to contain both the original SOREL20M dataset and the newly created pre-processed dataset use this alternative procedure:
1. First pre-process the dataset transforming it to the same format as in the previous command but saving it in multiple files on another disk (I used Google Colab drive for the original SOREL20M dataset and Google Drive for the pre-processed files).
You may now want get rid of the original dataset since it is not anymore needed. 
1. The final step needed to have the final pre-processed dataset (the same you would have gotten using the previous command), combine all the generated multipart files.

#### Pre-process Dataset Multipart

```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e preprocess_ds_multi \
-P ds_path=<path to the directory containing the meta.db file> \
-P destination_dir=<the directory where to save the pre-processed dataset files> \
-P training_n_samples=<max number of training data samples to use (if -1 -> takes all) (default: -1)> \
-P validation_n_samples=<max number of validation data samples to use (if -1 -> takes all) (default: -1)> \
-P test_n_samples=<max number of test data samples to use (if -1 -> takes all) (default: -1)> \
-P batch_size=<how many samples per batch to load (default: 8192)> \
-P n_batches=<number of batches to save in one single file (if -1 -> takes all) (default: 10)> \
-P remove_missing_features=<Strategy for removing missing samples, with meta.db entries but no associated features, from the data>
```
Note on remove_missing_features: it can be False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the database
in order to remove the data points with missing features; in case it is a filepath then a file (in Json format) will be used to
determine the data points with missing features.

#### Combine Dataset Multipart Files

```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e combine_ds_files \
-P ds_path=<local_multi_path> \
-P training_n_samples=<max number of training data samples to use (if -1 -> takes all) (default: -1)> \
-P validation_n_samples=<max number of validation data samples to use (if -1 -> takes all) (default: -1)> \
-P test_n_samples=<max number of test data samples to use (if -1 -> takes all) (default: -1)>
```

---
## Train Network

Command used to train the (chosen) feed-forward neural network on EMBER 2.0 features, optionally with additional targets as described in the ALOHA paper (https://arxiv.org/abs/1903.05700). SMART tags based on (https://arxiv.org/abs/1905.06262).
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e train_network \
-P ds_path=<path of the directory where to find the pre-processed dataset (containing .dat files)> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P gen_type=<generator (and dataset) class to use between 'base', 'alt1', 'alt2', 'alt3' (default: base)> \
-P run_id=<mlflow run id of a previously stopped run to resume (default: 0)> \
-P training_run=<training run identifier (default: 0)> \
-P batch_size=<how many samples per batch to load (default: 8192)> \
-P epochs=<how many epochs to train for (default: 10)> \
-P training_n_samples=<number of training samples to consider (0 -> take all) (default: 0)> \
-P validation_n_samples=<number of validation samples to consider (0 -> take all) (default: 0)> \
-P use_malicious_labels=<whether or not (1/0) to use malware/benignware labels as a target (default: 1)> \
-P use_count_labels=<whether or not (1/0) to use the counts as an additional target (default: 1)> \
-P use_tag_labels=<whether or not (1/0) to use the tags as additional targets (default: 1)> \
-P workers=<how many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())>
```

---
## Evaluate Network

Command used to produce and output (to a csv file) evaluation results for a trained feedforward neural network model.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e evaluate_network \
-P ds_path=<path of the directory where to find the pre-processed dataset (containing .dat files)> \
-P checkpoint_file=<path to the model checkpoint to load> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P gen_type=<generator (and dataset) class to use between 'base', 'alt1', 'alt2', 'alt3' (default: base)> \
-P batch_size=<how many samples per batch to load (default: 10)> \
-P test_n_samples=<number of test samples to consider (0 -> take all) (default: 0)> \
-P evaluate_malware=<whether or not (1/0) to record malware labels and predictions (default: 1)> \
-P evaluate_count=<whether or not (1/0) to record count labels and predictions (default: 1)> \
-P evaluate_tags=<whether or not (1/0) to use SMART tags as additional targets (default: 1)>
```

---
## Compute All Run Results

Command used to compute and plot all the per-tag and mean per-sample scores for a single model training run.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e plot_tag_result \
-P results_file=<path to results.csv containing the output of a model run> \
-P use_malicious_labels=<whether or not (1/0) to compute malware/benignware label scores (default: 1)> \
-P use_tag_labels=<whether or not (1/0) to compute the tag label scores (default: 1)>
```

---
## Plot All ROC Distributions

Command used to compute the mean and standard deviation of the TPR at a range of FPRS (the ROC curve) over several sets of results (at least 2 runs) for a given tag.
The run_to_filename_json file must have the following format:
```
{"run_id_0": "/full/path/to/results.csv/for/run/0/results.csv",
 "run_id_1": "/full/path/to/results.csv/for/run/1/results.csv",
  ...
}
```
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e plot_all_roc_distributions \
-P run_to_filename_json=<path to the run_to_filename_json file> \
-P use_malicious_labels=<whether or not (1/0) to compute malware/benignware label scores (default: 1)> \ 
-P use_tag_labels=<whether or not (1/0) to compute the tag label scores (default: 1)>
```

---
## Build Fresh Dataset

Command used to build a 'fresh' dataset retrieving samples from Malware Bazaar given a list of malware families stored in a configuration file.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e build_fresh_dataset \
-P dataset_dest_dir=<dir where to write the newly created dataset>
```

---
## Evaluate Fresh

Command used to produce and output (to a json file and a bunch of csv files) fresh dataset evaluation prediction and ranking results for a trained feedforward neural network model.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e evaluate_fresh \
-P ds_path=<path of the directory where to find the fresh dataset (containing .dat files)> \
-P checkpoint_path=<path to the model checkpoint to load> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P n_anchor_samples_per_family=<number of anchor samples per-family to use during prediction evaluation (default: 10)>
-P n_queries=<number of queries to do during ranking evaluation (default: 100)>
```

---
## Generator alt3 speed evaluation
Selecting different values for chunk_size and n_chunks has an impact on the speed of the generator alt3 and on the samples dispersion.
To select good values for chunk_size and n_chunks for your system you can use the combination of the following two commands which evaluates the generator alt3 speed on the target machine.
These functions will perform 'epochs' model training epochs using values for chunk_size and n_chunks got from two intervals and will plot 2 heatmaps: the first containing the average elapsed times and the second the average speeds.
When making the final decision on the aforementioned values it is better to consider a higher value for n_chunks in order to increase samples dispersion during shuffling.
The default values of `CHUNK_SIZE=256` and `CHUNKS=256` are hardcoded in the `generators_alt3.py` file. These should be good values in most cases. If you want to change them hardcode the new values in the code.

### Evaluate gen3 speed

Command used to evaluate generator alt3 speed changing values for 'chunk_size' and 'chunks' variables. The evaluation is done the number of epochs specified for each combination of values and the results averaged. The resulting elapsed times and speeds are save to a json file.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e evaluate_gen3_speed \
-P ds_path=<path of the directory where to find the fresh dataset (containing .dat files)> \
-P json_file_path=<Path to a new or an existent (from a previous run) json file to be used to store run evaluation elapsed times and speeds> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P batch_size=<How many samples per batch to load. (default: 8192)> \
-P min_mul=<Minimum product between chunks and chunk_size to consider (in # of batches). (default: 1)> \
-P max_mul=<Maximum product between chunks and chunk_size to consider (in # of batches). (default: 32)> \
-P epochs=<How many epochs to train for. (default: 1)> \
-P training_n_samples=<Number of training samples to consider (used to access the right files). (default: 0 -> all)> \
-P use_malicious_labels=<Whether or (1/0) not to use malware/benignware labels as a target. (default: 1)> \
-P use_count_labels=<Whether or not (1/0) to use the counts as an additional target. (default: 1)> \
-P use_tag_labels=<Whether or not (1/0) to use the tags as additional targets. (default: 1)> \
-P workers=<How many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())>
```

---
### Create gen3 heatmap

Command used to produce elapsed times and speeds heatmaps from the json file resulting from 'gen3_eval', which contains the times elapsed and speeds for a number of evaluation runs.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e create_gen3_heatmap \
-P json_file_path=<Path the json file containing the run evaluation elapsed times and speeds>
```

---

# Wiki
There is now a <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki' title='Wiki!'>📖wiki</a>!
