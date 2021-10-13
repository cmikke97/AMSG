# Copyright 2021, Crepaldi Michele.
#
# Developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision
# of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import configparser  # implements a basic configuration language for Python programs
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
import time  # provides various time-related functions
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
import psutil  # used for retrieving information on running processes and system utilization
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python

from nets.Contrastive_Model_net import Net
from nets.generators.fresh_generators import get_generator
from utils.ranking_metrics import (mean_reciprocal_rank, mean_average_precision,
                                   max_reciprocal_rank, min_reciprocal_rank,
                                   max_average_precision, min_average_precision)

# get config file path
model_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['general']['device']
N_SAMPLES = int(config['sorel20mDataset']['test_n_samples'])

try:
    # try getting layer sizes from config file
    layer_sizes = json.loads(config['mtje']['layer_sizes'])
except json.JSONDecodeError:
    # if the option is not present in the config file set layer sizes to None
    layer_sizes = None

# instantiate run additional parameters dict setting values got from config file
run_additional_params = {
    'layer_sizes': layer_sizes,
    'dropout_p': float(config['mtje']['dropout_p']),
    'activation_function': config['mtje']['activation_function'],
    'normalization_function': config['mtje']['normalization_function'],
    'optimizer': config['contrastiveLearning']['optimizer'],
    'lr': float(config['contrastiveLearning']['lr']),
    'momentum': float(config['contrastiveLearning']['momentum']),
    'weight_decay': float(config['contrastiveLearning']['weight_decay']),
    'hard': int(config['contrastiveLearning']['hard']),
    'margin': float(config['contrastiveLearning']['margin']),
    'squared': int(config['contrastiveLearning']['squared'])
}


def compute_ranking_scores(rank_per_query):  # list of ranks computed by the model evaluation procedure
    """ Compute ranking scores (MRR and MAP) and a bunch of interesting ranks to save to file from a list of ranks.

    Args:
        rank_per_query: List of ranks computed by the model evaluation procedure
    Returns:
        ranking scores (in a dict) and a dict of interesting ranks to save to file.
    """

    # compute binarized (0/1) relevance scores
    rs = [np.asarray([i == rank['ground_truth_label'] for i in rank['rank_labels']], dtype=np.dtype(int))
          for rank in rank_per_query]

    # compute and log MRR and MAP scores
    ranking_scores = {'MRR': mean_reciprocal_rank(rs), 'MAP': mean_average_precision(rs)}

    # compute a bunch of indexes for interesting queries to save in csv files as examples
    max_rr, max_rr_idx = max_reciprocal_rank(rs)
    min_rr, min_rr_idx = min_reciprocal_rank(rs)
    max_ap, max_ap_idx = max_average_precision(rs)
    min_ap, min_ap_idx = min_average_precision(rs)
    # save indexes (and values) just computed to a dict
    queries_indexes = {
        'max_rr': {'value': max_rr, 'index': max_rr_idx},
        'min_rr': {'value': min_rr, 'index': min_rr_idx},
        'max_ap': {'value': max_ap, 'index': max_ap_idx},
        'min_ap': {'value': min_ap, 'index': min_ap_idx}
    }

    # get interesting queries
    ranks_to_save = {
        key: {
            'value': scores['value'],
            'rank': rank_per_query[scores['index']]
        }
        for key, scores in queries_indexes.items()
    }

    # return computed scores and interesting queries
    return ranking_scores, ranks_to_save


def normalize_results(labels,
                      predictions):
    """ Normalize results to make them easier to be saved to file.

    Args:
        labels: Array-like (tensor or numpy array) object containing the ground truth labels
        predictions: Array-like (tensor or numpy array) object containing the model predictions

    Returns:
        Dictionary containing the normalized labels and predictions tensors.
    """

    # initialize the result value dict detaching and copying the labels tensor
    rv = {
        'label': Net.detach_and_copy_array(labels)
    }

    # for each prediction in the 'predictions' dict
    for k, v in predictions.items():
        # save into the return value dict the current model prediction tensor after having detached and copied it
        rv['{}-NN_pred'.format(k)] = Net.detach_and_copy_array(v)

    # return 'return value'
    return rv


@baker.command
def evaluate_network(fresh_ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                     checkpoint_path,  # path to the model checkpoint to load
                     training_run=0,  # training run identifier
                     train_split_proportion=7,  # train subsplit proportion value
                     valid_split_proportion=1,  # validation subsplit proportion value
                     test_split_proportion=2,  # test subsplit proportion value
                     batch_size=250,  # how many samples per batch to load
                     rank_size=20,  # size (number of samples) of the ranking to produce
                     knn_k_min=1,  # minimum value of k to use when applying the k-nn algorithm
                     knn_k_max=11,  # maximum value of k to use when applying the k-nn algorithm
                     # if provided, seed random number generation with this value (default: None, no seeding)
                     random_seed=None,
                     # how many worker (threads) the dataloader uses (default: 0 -> use multiprocessing.cpu_count())
                     workers=0):
    """ Evaluate the model on both the family prediction task and on the family ranking task.

    Args:
        fresh_ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        training_run: Training run identifier (default: 0)
        train_split_proportion: Train subsplit proportion value (default: 7)
        valid_split_proportion: Validation subsplit proportion value (default: 1)
        test_split_proportion: Test subsplit proportion value (default: 2)
        batch_size: How many samples per batch to load (default: 250)
        rank_size: Size (number of samples) of the ranking to produce (default: 20)
        knn_k_min: Minimum value of k to use when applying the k-nn algorithm (default: 1)
        knn_k_max: Maximum value of k to use when applying the k-nn algorithm (default: 11)
        random_seed: If provided, seed random number generation with this value (default: None, no seeding)
        workers: How many worker (threads) the dataloader uses (default: 0 -> use multiprocessing.cpu_count())
    """

    # start mlflow run
    with mlflow.start_run() as mlrun:
        # if the split proportions are not as expected raise ValueError
        if train_split_proportion <= 0 or valid_split_proportion <= 0 or test_split_proportion <= 0:
            raise ValueError('train, valid and test split proportions must be positive integers.')

        # the rank size must be smaller (or at most equal) to the selected batch size
        if rank_size > batch_size:
            raise ValueError('rank size should be smaller or equal to the batch size.')

        # generate the dataset split proportions (list)
        dataset_split_proportions = [train_split_proportion, valid_split_proportion, test_split_proportion]

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('...instantiating siamese network for contrastive evaluation run n. {}'.format(training_run))

        # create fresh dataset generators
        train_generator, _, test_generator = get_generator(ds_root=fresh_ds_path,
                                                           splits=dataset_split_proportions,
                                                           batch_size=batch_size,
                                                           return_shas=True,
                                                           num_workers=workers,
                                                           shuffle=True)  # shuffle samples

        # get label to signature function from the test dataset (used to convert numerical labels to family names)
        label_to_sig = test_generator.dataset.label_to_sig

        # get total number of families
        n_families = test_generator.dataset.n_families

        # create contrastive (siamese) mtjeNet model
        model = Net(feature_dimension=2381,
                    embedding_dimension=32,
                    layer_sizes=run_additional_params['layer_sizes'],
                    dropout_p=run_additional_params['dropout_p'],
                    activation_function=run_additional_params['activation_function'],
                    normalization_function=run_additional_params['normalization_function'])

        # load model checkpoint
        model.load_state_dict(torch.load(checkpoint_path))

        # allocate model to selected device (CPU or GPU)
        model.to(device)

        logger.info('Evaluating contrastive learning model..')
        # set model into evaluation mode
        model.eval()

        # get number of steps per epoch (# of total batches) from test generator
        test_steps_per_epoch = len(test_generator)

        # get number of steps per epoch (# of total batches) from train generator
        train_steps_per_epoch = len(train_generator)

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            # compute result file path
            filename = os.path.join(tempdir, 'results.csv')

            # create and open the results file in write mode
            with open(filename, 'w') as f:
                first_batch = True

                ranks = []

                # set current epoch start time
                start_time = time.time()

                # for all mini-batches of samples of the test generator
                for i, (query_shas, query_features, query_labels) in enumerate(test_generator):
                    # get the query samples shas
                    query_shas = np.asarray(query_shas)
                    # transfer query features and labels to selected device
                    query_features = deepcopy(query_features).to(device)
                    query_labels = deepcopy(query_labels.long()).to(device)

                    with torch.no_grad():  # disable gradient calculation
                        # perform a forward pass through the network to get the query samples embeddings
                        query_pe_embeddings = model(query_features)

                    # initialize top samples arrays with null value
                    top_shas = None
                    top_labels = None
                    top_distances = None

                    predictions = {}

                    # for all mini-batches of data from the train generator
                    for j, (anchor_shas, anchor_features, anchor_labels) in enumerate(train_generator):
                        # get the anchor samples shas
                        anchor_shas = np.asarray(anchor_shas)
                        # transfer anchor features to selected device
                        anchor_features = anchor_features.to(device)

                        with torch.no_grad():  # disable gradient calculation
                            # perform a forward pass through the network to get the anchor embeddings
                            anchor_pe_embeddings = model(anchor_features)

                        # compute euclidean distances between query and anchor samples
                        distances = torch.cdist(query_pe_embeddings, anchor_pe_embeddings, p=2.0)

                        # if top distances is none
                        if top_distances is None:
                            # assign to top distances the current computed distances
                            top_distances = distances

                            # compute array of indices which sort the distances in ascending order
                            indices = top_distances.argsort(dim=1)

                            # obtain the shas of the first 'rank_size' most similar query samples
                            # (based on the computed indices)
                            top_shas = np.concatenate([np.expand_dims(
                                np.repeat(np.expand_dims(anchor_shas, axis=0), query_shas.shape[0], axis=0)[x, y],
                                axis=0)
                                for x, row in enumerate(indices[:, :rank_size])
                                for y in row]).reshape(-1, rank_size)

                            # obtain the labels of the first 'rank_size' most similar query samples
                            # (based on the computed indices)
                            top_labels = torch.cat([anchor_labels.repeat(query_labels.shape[0], 1)[x, y].unsqueeze(0)
                                                    for x, row in enumerate(indices[:, :rank_size])
                                                    for y in row]).view(-1, rank_size)

                            # obtain the distances of the first 'rank_size' most similar query samples to the current
                            # anchor (based on the computed indices)
                            top_distances = torch.cat([top_distances[x, y].unsqueeze(0)
                                                       for x, row in enumerate(indices[:, :rank_size])
                                                       for y in row]).view(-1, rank_size)
                        else:
                            # concatenate the current shas to the top shas array
                            top_shas = np.concatenate((top_shas, np.repeat(np.expand_dims(anchor_shas, axis=0),
                                                                           top_shas.shape[0], axis=0)), axis=1)
                            # concatenate the current labels to the top labels tensor
                            top_labels = torch.cat((top_labels, anchor_labels.repeat(top_labels.size()[0], 1)), dim=1)
                            # concatenate the current distances to the top distances tensor
                            top_distances = torch.cat((top_distances, distances), dim=1)

                            # compute array of indices which sort the distances in ascending order
                            indices = top_distances.argsort(dim=1)

                            # obtain the labels of the first 'rank_size' most similar query samples
                            # (based on the computed indices)
                            top_shas = np.concatenate([np.expand_dims(top_shas[x, y], axis=0)
                                                       for x, row in enumerate(indices[:, :rank_size])
                                                       for y in row]).reshape(-1, rank_size)

                            # obtain the labels of the first 'rank_size' most similar query samples
                            # (based on the computed indices)
                            top_labels = torch.cat([top_labels[x, y].unsqueeze(0)
                                                    for x, row in enumerate(indices[:, :rank_size])
                                                    for y in row]).view(-1, rank_size)

                            # obtain the distances of the first 'rank_size' most similar query samples to the current
                            # anchor (based on the computed indices)
                            top_distances = torch.cat([top_distances[x, y].unsqueeze(0)
                                                       for x, row in enumerate(indices[:, :rank_size])
                                                       for y in row]).view(-1, rank_size)

                    # for all query samples
                    for k, s in enumerate(query_shas):
                        # save ranking
                        ranks.append({
                            'query_sha': s,
                            'ground_truth_label': int(query_labels[k].item()),
                            'ground_truth_family': label_to_sig(int(query_labels[k].item())),
                            'rank_shas': top_shas[k].tolist(),
                            'rank_labels': [int(lab.item()) for lab in top_labels[k]],
                            'rank_families': [label_to_sig(int(lab.item())) for lab in top_labels[k]]
                        })

                    # for all odd values of k from knn_k_min to knn_k_max (included)
                    for k in range(knn_k_min if knn_k_min % 2 else knn_k_min + 1, knn_k_max + 1, 2):
                        # get the first k labels from the top labels tensor
                        knn_labels = top_labels[:, :k]
                        # get the first k distances from the top distances tensor and raise them to the power of -2
                        knn_weights = torch.pow(top_distances[:, :k], -2)

                        # initialize per family-scores to 0
                        knn_scores = torch.zeros((knn_labels.shape[0], n_families)).to(device)
                        # for all top k labels
                        for idx, labs in enumerate(knn_labels):
                            # compute the per-family sum of distance weights
                            knn_scores[idx].index_add_(0, torch.tensor([int(lab.item()) for lab in labs]).to(device),
                                                       knn_weights[idx])

                        # save as prediction the family with the maximum score
                        predictions[str(k)] = torch.argmax(knn_scores, dim=1)

                    # compute current epoch elapsed time (in seconds)
                    elapsed_time = time.time() - start_time

                    # write on standard out the elapsed time, predicted total epoch completion time, current mean speed
                    # and main memory usage
                    sys.stdout.write('\r Contrastive learning evaluation: {}/{} '.format(i + 1, test_steps_per_epoch)
                                     + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                     .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                             time.strftime("%H:%M:%S",  # predict total epoch completion time
                                                           time.gmtime(test_steps_per_epoch * elapsed_time / (i + 1))),
                                             (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                             psutil.virtual_memory().percent))  # get percentage of main memory used

                    # flush standard output
                    sys.stdout.flush()

                    # normalize the results
                    results = normalize_results(query_labels, predictions)

                    # store results into a pandas dataframe (indexed by the sha265 keys) and then save it as csv into
                    # file f (inserting the header only if this is the first batch in the loop)
                    pd.DataFrame(results, index=query_shas).to_csv(f, header=first_batch)

                    first_batch = False

                # compute ranking scores (MAP and MRR) and interesting ranks to save
                ranking_scores, ranks_to_save = compute_ranking_scores(ranks)

                # log ranking scores
                mlflow.log_metric('MRR', float(ranking_scores['MRR']))
                mlflow.log_metric('MAP', float(ranking_scores['MAP']))

                # compute example rank dataframes
                dataframes = {
                    key: pd.DataFrame({"sha256": value['rank']['rank_shas'],
                                       "label": value['rank']['rank_labels'],
                                       "family": value['rank']['rank_families']})
                    for key, value in ranks_to_save.items()
                }

                # compute example ranks metadata
                metadata = {
                    key: pd.Series([
                        '{}: {}'.format(key, value['value']),
                        'Query sample sha256: {}'.format(value['rank']['query_sha']),
                        'Ground truth label: {}'.format(value['rank']['ground_truth_label']),
                        'Ground truth family: {}'.format(value['rank']['ground_truth_family'])
                    ])
                    for key, value in ranks_to_save.items()
                }

                logger.info('Saving results..')

                # for each example rank
                for df_key, df_val in dataframes.items():
                    # retrieve metadata
                    meta = metadata[df_key]

                    # create file name
                    df_filename = os.path.join(tempdir, '{}_example_rank.csv'.format(df_key))

                    # open dataframe dest file and write both metadata and dataframe to it
                    with open(df_filename, 'w') as df_f:
                        meta.to_csv(df_f, index=False)
                        df_val.to_csv(df_f)

                    # log results file as artifact
                    mlflow.log_artifact(df_filename, artifact_path="contrastive_learning_results")

                # log results file as artifact
                mlflow.log_artifact(filename, artifact_path="contrastive_learning_results")

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
