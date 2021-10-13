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
import importlib  # provides the implementation of the import statement in Python source code
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

from nets.generators.fresh_dataset import Dataset
from nets.generators.fresh_generators import get_generator
from utils.ranking_metrics import (mean_reciprocal_rank, mean_average_precision,
                                   max_reciprocal_rank, min_reciprocal_rank,
                                   max_average_precision, min_average_precision)

np.set_printoptions(threshold=sys.maxsize)
np.set_printoptions(linewidth=sys.maxsize)

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

all_tags = Dataset.tags


def distance_to_similarity(distances,  # tensor containing the distances calculated between two embeddings
                           a=1.0,  # inversion multiplication factor
                           function='exp'):  # inversion function to use. Possible values are: 'exp', 'inv' or 'inv_pow'
    """ Calculate similarity scores from distances by using an inversion function.

    Args:
        distances: Tensor containing the distances calculated between two embeddings
        a: Inversion multiplication factor (default: 1.0)
        function: Inversion function to use. Possible values are: 'exp', 'inv' or 'inv_pow' (default: 'exp')
    Returns:
        Similarity scores computed from the provided distances.
    """

    if function == 'exp':
        similarity = torch.exp(torch.div(distances, -a))
    elif function == 'inv':
        similarity = torch.pow(torch.add(torch.div(distances, a), 1.0), -1.0)
    elif function == 'inv_pow':
        similarity = torch.pow(torch.add(torch.div(torch.pow(distances, 2.0), a), 1.0), -1.0)
    else:
        raise ValueError('Unknown distance-to-similarity function {}.'.format(function))
    return similarity


# network type (possible values: mtje, mtje_cosine, mtje_pairwise_distance, aloha)
def import_modules(net_type):
    """ Dynamically import network depending on the provided argument.

    Args:
        net_type: Network type (possible values: mtje, mtje_cosine, mtje_pairwise_distance, aloha)
    Returns:
        Net imported from selected modules.
    """

    # set network module name based on the current network type
    if net_type.lower() == 'mtje':
        net_type = 'mtje'
        net_module_name = 'nets.MTJE_net'
    elif net_type.lower() == 'mtje_cosine':
        net_type = 'mtje'
        net_module_name = 'nets.MTJE_net_cosine'
    elif net_type.lower() == 'mtje_pairwise_distance':
        net_type = 'mtje'
        net_module_name = 'nets.MTJE_net_pairwise_distance'
    elif net_type.lower() == 'aloha':
        net_type = 'aloha'
        net_module_name = "nets.ALOHA_net"
    else:  # if the network type is neither mtje nor aloha raise ValueError
        raise ValueError('Unknown Network type. Possible values: "mtje", "mtje_cosine" or "mtje_pairwise_distance".'
                         'Got {} '.format(net_type))

    # import net module
    net_module = importlib.import_module(net_module_name)
    # get 'Net' class from net module
    Net = getattr(net_module, 'Net')

    try:
        # try getting layer sizes from config file
        layer_sizes = json.loads(config[net_type]['layer_sizes'])
    except json.JSONDecodeError:
        # if the option is not present in the config file set layer sizes to None
        layer_sizes = None

    # instantiate run additional parameters dict setting values got from config file
    run_additional_params = {
        'layer_sizes': layer_sizes,
        'dropout_p': float(config[net_type]['dropout_p']),
        'activation_function': config[net_type]['activation_function'],
        'normalization_function': config[net_type]['normalization_function']
    }

    # return classes, functions and variables imported
    return Net, run_additional_params


def detach_and_copy_array(array):  # numpy array or pytorch tensor to copy
    """ Detach numpy array or pytorch tensor and return a deep copy of it.

    Args:
        array: Numpy array or pytorch tensor to copy
    Returns:
        Deep copy of the array.
    """

    if isinstance(array, torch.Tensor):  # if the provided array is of type Tensor
        # return a copy of the array after having detached it, passed it to the cpu and finally flattened
        return deepcopy(array.cpu().detach().numpy()).ravel()
    elif isinstance(array, np.ndarray):  # else if it is of type ndarray
        # return a copy of the array after having flattened it
        return deepcopy(array).ravel()
    else:
        # otherwise raise an exception
        raise ValueError("Got array of unknown type {}".format(type(array)))


def normalize_embeddings(results_dict):  # results (predicted labels) dictionary
    """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
    that pandas can convert to a DataFrame.

    Args:
        results_dict: Results (predicted labels) dictionary
    Returns:
        Dictionary containing embeddings.
    """
    # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
    # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

    rv = {}

    for column in range(32):  # for all the tags
        # normalize predicted tag array and save it into rv
        rv['embed_{}'.format(column)] = detach_and_copy_array(results_dict['embedding'][:, column])

    return rv


def get_samples(model,
                generator,
                n_families,
                n_samples_to_get,
                other=None):
    """ Get 'n_samples_to_get' from the prodived 'generator' among the samples not in 'other'.

    Args:
        model: Model to evaluate
        generator: Dataset generator (dataloader) containing the data to retrieve (fresh dataset)
        n_families: Number of families contained in the fresh dataset
        n_samples_to_get: Number of samples to get per family from the Generator
        other: Dictionary containing samples not to provide as result (default: None)
    Returns:
        Dictionary containing the samples retrieved from the provided Generator
    """

    # initialize samples dict to the null value
    samples = None
    # initialize list of samples fot per family to all zeros
    samples_families = [0 for _ in range(n_families)]

    # for all the mini-batches of data from the generator (Dataloader)
    for shas, features, labels in generator:
        # if other was provided
        if other is not None:
            # compute indices of all samples not in 'other'
            indices = [i for i, sha in enumerate(shas) if sha not in other['shas']]

            # select all samples not in 'other'
            shas = [shas[i] for i in indices]
            features = features[indices]
            labels = labels[indices]

        # transfer features to selected device
        features = features.to(device)

        # perform a forward pass through the network and get predictions
        predictions = model.get_embedding(features)

        # get embeddings
        embeddings = predictions['embedding']

        # for each family
        for n in range(n_families):
            # if the current family has at leas n_samples_to_get samples, go to the next one
            if samples_families[n] >= n_samples_to_get:
                continue

            # get the indices of all samples with the same label as the current family
            indices = [i for i, label in enumerate(labels) if label == n]
            # get the first n_samples_to_get sample indices (or less if there are not enough indices)
            indices = indices[:n_samples_to_get] if len(indices) > n_samples_to_get else indices

            # the first iteration assign the first samples' shas, labels and embeddings
            if samples is None:
                samples = {
                    'shas': [shas[i] for i in indices],
                    'labels': labels[indices],
                    'features': features[indices],
                    'embeddings': embeddings[indices]
                }
            else:  # from the second iteration on, instead, append (concatenate) them
                samples['shas'].extend([shas[i] for i in indices])
                samples['labels'] = torch.cat((samples['labels'], labels[indices]), 0)
                samples['features'] = torch.cat((samples['features'], features[indices]), 0)
                samples['embeddings'] = torch.cat((samples['embeddings'], embeddings[indices]), 0)

            # update the count of samples for the current family
            samples_families[n] += len(indices)

        # if all families have at least n_samples_to_get samples, break
        if all(n >= n_samples_to_get for n in samples_families):
            break

    return samples


def evaluate_fresh_scores(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                          checkpoint_path,  # path to the model checkpoint to load
                          # network to use between 'mtje', 'mtje_cosine', 'mtje_pairwise_distance' and 'aloha'
                          net_type='mtje',
                          n_query_samples=23,  # number of query samples to retrieve, per-family
                          min_n_anchor_samples=1,  # minimum number of anchor samples to use, per-family
                          max_n_anchor_samples=10,  # maximum number of anchor samples to use, per-family
                          n_evaluations=15,  # number of evaluations to perform (for uncertainty estimates)
                          batch_size=1000):  # how many samples per batch to load
    """ Evaluate model on the Malware Family Prediction task.

    Args:
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'mtje', 'mtje_cosine', 'mtje_pairwise_distance' and 'aloha' (default: 'mtje')
        n_query_samples: Number of query samples to retrieve, per-family (default: 23)
        min_n_anchor_samples: Minimum number of anchor samples to use, per-family (default: 1)
        max_n_anchor_samples: Maximum number of anchor samples to use, per-family (default: 10)
        n_evaluations: Number of evaluations to perform (for uncertainty estimates) (default: 15)
        batch_size: How many samples per batch to load (default: 1000)

    Returns:

    """

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net, run_additional_params = import_modules(net_type=net_type)

    # instantiate model
    model = Net(use_malware=False,
                use_counts=False,
                use_tags=True,
                n_tags=len(Dataset.tags),
                feature_dimension=2381,
                embedding_dimension=32,
                layer_sizes=run_additional_params['layer_sizes'],
                dropout_p=run_additional_params['dropout_p'],
                activation_function=run_additional_params['activation_function'],
                normalization_function=run_additional_params['normalization_function'])

    # load model parameters from checkpoint
    model.load_state_dict(torch.load(checkpoint_path))

    # allocate model to selected device (CPU or GPU)
    model.to(device)

    # set the model mode to 'eval'
    model.eval()

    # create fresh dataset generator
    generator = get_generator(ds_root=ds_path,
                              batch_size=batch_size,
                              return_shas=True,
                              shuffle=True)  # shuffle samples

    # get label to signature function from the dataset (used to convert numerical labels to family names)
    label_to_sig = generator.dataset.label_to_sig

    # get total number of families
    n_families = generator.dataset.n_families

    is_aloha_run = net_type.lower() == 'aloha'

    # if the total number of anchor samples is greater than the dataset size, error
    if max_n_anchor_samples * n_families >= generator.dataset.__len__():
        raise ValueError('The selected maximum number of anchor samples is too high. -> max_n_anchor_samples ({}) x '
                         'num_families ({}) = {} > dataset size ({}).'.format(max_n_anchor_samples,
                                                                              n_families,
                                                                              max_n_anchor_samples * n_families,
                                                                              generator.dataset.__len__()))

    # if the min number of anchor samples to get is not as expected raise ValueError
    if min_n_anchor_samples <= 0:
        raise ValueError('Minimum number of anchor samples must be a positive integer. Found {}.'.format(
            min_n_anchor_samples))

    # if the number of query samples to get is not as expected raise ValueError
    if n_query_samples <= 0:
        raise ValueError('Number of query samples must be a positive integer. Found: {}.'.format(
            n_query_samples))

    predictions = {}
    # for each value of n anchor samples from 'min n anchor' to 'max n anchor'
    for k, n_anchor_samples in enumerate(range(min_n_anchor_samples, max_n_anchor_samples + 1)):
        # initialize current predictions to the empty list
        predictions[str(n_anchor_samples)] = []

        # set current epoch start time
        start_time = time.time()

        # for 'n evaluations'
        for j in range(n_evaluations):
            # get 'n_anchor_samples' from the generator (already extracting features etc..)
            anchors = get_samples(model, generator, n_families, n_anchor_samples)
            # get 'n_query_samples' from the generator (already extracting features etc..) among the
            # samples not in 'anchors'
            queries = get_samples(model, generator, n_families, n_query_samples, other=anchors)

            # if the model being evaluated is aloha
            if is_aloha_run:
                # compute the similarity scores between the samples and anchors' embeddings using the
                # matrix multiplication function
                similarity_scores = torch.matmul(queries['embeddings'], anchors['embeddings'].T).cpu().detach()
            else:
                # compute the similarity scores between the samples and anchors' embeddings using the model's
                # get_similarity function
                similarity_scores = model.get_similarity(queries['embeddings'],
                                                         anchors['embeddings'])['similarity'].cpu().detach()

            # get the sha256 hashes of the query samples
            shas = queries['shas']
            # get the labels of the query samples
            labels = queries['labels']

            # compute the current predictions getting the labels of the anchors samples with the highest
            # similarity score
            curr_predictions = anchors['labels'][torch.argmax(similarity_scores, dim=1)]
            # compute the probabilities applying the softmax function of the similarity scores of the anchors samples
            # with the highest similarity scores
            curr_probabilities = torch.nn.Softmax(dim=1)(torch.tensor([[torch.max(
                sims[[j for j in range(len(sims)) if anchors['labels'][j] == i]]).item() for i in range(n_families)] for
                                                                       sims in similarity_scores]))

            # construct prediction dictionary for the current number of anchor samples and append it to the
            # global predictions
            predictions[str(n_anchor_samples)].append({
                'families': [label_to_sig(lab) for lab in range(n_families)],
                'shas': shas,
                'labels': labels.tolist(),
                'predictions': curr_predictions.tolist(),
                'probabilities': curr_probabilities.tolist()
            })

            # compute current epoch elapsed time (in seconds)
            elapsed_time = time.time() - start_time

            # write on standard out the loss string + other information
            # (elapsed time, predicted total epoch completion time, current mean speed and main memory usage)
            sys.stdout.write('\r Family predictions: {}/{} {}/{} '.format(
                k + 1, max_n_anchor_samples + 1 - min_n_anchor_samples,
                j + 1, n_evaluations)
                             + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                             .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                     time.strftime("%H:%M:%S",  # predict total epoch completion time
                                                   time.gmtime(n_evaluations * elapsed_time / (j + 1))),
                                     (j + 1) / elapsed_time,  # compute current mean speed (it/s)
                                     psutil.virtual_memory().percent))  # get percentage of main memory used

            # flush standard output
            sys.stdout.flush()

        print()

    # create temporary direcyory
    with tempfile.TemporaryDirectory() as tmpdir:
        # compute result file path
        predictions_result_json_path = os.path.join(tmpdir, 'fresh_prediction_results.json')

        # open result file
        with open(predictions_result_json_path, 'w') as outfile:
            # dump the global predictions to json file
            json.dump(predictions, outfile)

        mlflow.log_artifact(predictions_result_json_path, 'fresh_prediction_results')


def compute_ranking_scores(ranking_scores,
                           global_ranks_to_save,
                           rank_per_query):
    """ Compute ranking scores (MRR and MAP) and a bunch of interesting ranks to save to file from a list of ranks.

    Args:
        ranking_scores: Ranking scores previously computed
        global_ranks_to_save: Global interesting ranks to save to file
        rank_per_query: List of ranks computed by the model evaluation procedure
    Returns:
        ranking scores (in a dict) and a dict of global interesting ranks to save to file
    """

    # compute binarized (0/1) relevance scores
    rs = [np.asarray([i == rank['ground_truth_label'] for i in rank['rank_labels']], dtype=np.dtype(int))
          for rank in rank_per_query]

    # compute and log MRR and MAP scores
    ranking_scores['MRR'].append(mean_reciprocal_rank(rs))
    ranking_scores['MAP'].append(mean_average_precision(rs))

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

    # if the global ranks to save dict is none set it to the current ranks to save
    if global_ranks_to_save is None:
        global_ranks_to_save = ranks_to_save
    else:
        # otherwise select from the current ranks to save the ones that are more 'interesting' than those
        # already in the global ranks to save dict
        if ranks_to_save['max_rr']['value'] > global_ranks_to_save['max_rr']['value']:
            global_ranks_to_save['max_rr']['value'] = ranks_to_save['max_rr']['value']
            global_ranks_to_save['max_rr']['rank'] = ranks_to_save['max_rr']['rank']
        if ranks_to_save['min_rr']['value'] < global_ranks_to_save['min_rr']['value']:
            global_ranks_to_save['min_rr']['value'] = ranks_to_save['min_rr']['value']
            global_ranks_to_save['min_rr']['rank'] = ranks_to_save['min_rr']['rank']
        if ranks_to_save['max_ap']['value'] > global_ranks_to_save['max_ap']['value']:
            global_ranks_to_save['max_ap']['value'] = ranks_to_save['max_ap']['value']
            global_ranks_to_save['max_ap']['rank'] = ranks_to_save['max_ap']['rank']
        if ranks_to_save['min_ap']['value'] < global_ranks_to_save['min_ap']['value']:
            global_ranks_to_save['min_ap']['value'] = ranks_to_save['min_ap']['value']
            global_ranks_to_save['min_ap']['rank'] = ranks_to_save['min_ap']['rank']

    # return computed ranking scores and global ranks to save dict
    return ranking_scores, global_ranks_to_save


def evaluate_fresh_rankings(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                            checkpoint_path,  # path to the model checkpoint to load
                            # network to use between 'mtje', 'mtje_cosine', 'mtje_pairwise_distance' and 'aloha'
                            net_type='mtje',
                            n_query_samples=23,  # number of query samples per-family to consider
                            n_evaluations=15,  # number of evaluations to perform (for uncertainty estimates)
                            batch_size=1000):  # how many samples per batch to load
    """ Evaluate model on the Malware Family ranking task.

    Args:
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'mtje', 'mtje_cosine', 'mtje_pairwise_distance' and 'aloha'. (default: 'mtje')
        n_query_samples: Number of query samples per-family to consider (default: 23)
        n_evaluations: Number of evaluations to perform (for uncertainty estimates) (default: 15)
        batch_size: How many samples per batch to load (default: 1000)
    """

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net, run_additional_params = import_modules(net_type=net_type)

    # instantiate model
    model = Net(use_malware=False,
                use_counts=False,
                use_tags=True,
                n_tags=len(Dataset.tags),
                feature_dimension=2381,
                embedding_dimension=32,
                layer_sizes=run_additional_params['layer_sizes'],
                dropout_p=run_additional_params['dropout_p'],
                activation_function=run_additional_params['activation_function'],
                normalization_function=run_additional_params['normalization_function'])

    # load model parameters from checkpoint
    model.load_state_dict(torch.load(checkpoint_path))

    # allocate model to selected device (CPU or GPU)
    model.to(device)

    # set the model mode to 'eval'
    model.eval()

    # create fresh dataset generator
    generator = get_generator(ds_root=ds_path,
                              batch_size=batch_size,
                              return_shas=True,
                              shuffle=True)  # shuffle samples

    # get label to signature function from the dataset (used to convert numerical labels to family names)
    label_to_sig = generator.dataset.label_to_sig

    # get total number of families
    n_families = generator.dataset.n_families

    is_aloha_run = net_type.lower() == 'aloha'

    # if the total number of anchor samples is greater than the dataset size, error
    if n_query_samples * n_families >= generator.dataset.__len__():
        raise ValueError('The selected maximum number of query samples is too high. -> n_query_samples ({}) x '
                         'num_families ({}) = {} > dataset size ({}).'.format(n_query_samples,
                                                                              n_families,
                                                                              n_query_samples * n_families,
                                                                              generator.dataset.__len__()))

    ranking_scores = {'MRR': [], 'MAP': []}
    global_ranks_to_save = None

    # set current epoch start time
    start_time = time.time()
    for j in range(n_evaluations):
        # set queries and rank_per_query dicts to null value
        queries = get_samples(model, generator, n_families, n_query_samples)

        rank_per_query = []
        # for all the batches in the generator (Dataloader)
        for shas, features, labels in generator:
            # transfer features to selected device
            features = features.to(device)

            # perform a forward pass through the network and get predictions
            predictions = model.get_embedding(features)

            # get embeddings
            embeddings = predictions['embedding']

            if is_aloha_run:
                similarity_scores = torch.matmul(queries['embeddings'], embeddings.T).cpu().detach()
            else:
                # compute the similarity scores between the samples and anchors' embeddings using the model's
                # get_similarity function
                similarity_scores = model.get_similarity(queries['embeddings'],
                                                         embeddings)['similarity'].cpu().detach()

            # get ranks per query sample:
            # for each query sample -> order samples labels/shas based on the similarity measure
            # (skipping the query sample itself)
            for i, s in enumerate(queries['shas']):
                indices = -similarity_scores[i, [j for j in range(len(similarity_scores[i])) if shas[j] != s]].argsort()
                rank_per_query.append({
                    'query_sha': s,
                    'ground_truth_label': int(queries['labels'][i].item()),
                    'ground_truth_family': label_to_sig(int(queries['labels'][i].item())),
                    'rank_shas': np.asarray(shas, dtype=np.dtype('U64'))[indices].tolist(),
                    'rank_labels': [int(lab) for lab in labels[indices]],
                    'rank_families': [label_to_sig(int(lab.item())) for lab in labels[indices]]
                })

        # compute ranking scores and global ranks to save
        ranking_scores, global_ranks_to_save = compute_ranking_scores(ranking_scores,
                                                                      global_ranks_to_save,
                                                                      rank_per_query)

        # compute current epoch elapsed time (in seconds)
        elapsed_time = time.time() - start_time

        params_str = 'queries: {}'.format(n_query_samples)
        scores_str = ' | MRR: {:7.4f}, MAP: {:7.4f} | mean MRR: {:7.4f}, mean MAP: {:7.4f}'.format(
            ranking_scores['MRR'][-1],
            ranking_scores['MAP'][-1],
            np.mean(ranking_scores['MRR'], dtype=np.float32),
            np.mean(ranking_scores['MAP'], dtype=np.float32))

        # write on standard out the scores string + other information
        # (elapsed time, predicted total epoch completion time, current mean speed and main memory usage)
        sys.stdout.write('\r Family ranking: {}/{} '.format(j + 1, len(range(n_evaluations)))
                         + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                         .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                 time.strftime("%H:%M:%S",  # predict total epoch completion time
                                               time.gmtime(len(range(n_evaluations)) * elapsed_time / (j + 1))),
                                 (j + 1) / elapsed_time,  # compute current mean speed (it/s)
                                 psutil.virtual_memory().percent)  # get percentage of main memory used
                         + params_str + scores_str)  # append params and scores strings

        # flush standard output
        sys.stdout.flush()

    print()

    # log some metrics
    mlflow.log_metric('MRR_mean', float(np.mean(ranking_scores['MRR'])))
    mlflow.log_metric('MRR_std', float(np.std(ranking_scores['MRR'])))
    mlflow.log_metric('MAP_mean', float(np.mean(ranking_scores['MAP'])))
    mlflow.log_metric('MAP_std', float(np.std(ranking_scores['MAP'])))

    # compute example ranks dataframes
    dataframes = {
        key: pd.DataFrame({"sha256": value['rank']['rank_shas'],
                           "label": value['rank']['rank_labels'],
                           "family": value['rank']['rank_families']})
        for key, value in global_ranks_to_save.items()
    }

    # compute example ranks metadata
    metadata = {
        key: pd.Series([
            '{}: {}'.format(key, value['value']),
            'Query sample sha256: {}'.format(value['rank']['query_sha']),
            'Ground truth label: {}'.format(value['rank']['ground_truth_label']),
            'Ground truth family: {}'.format(value['rank']['ground_truth_family'])
        ])
        for key, value in global_ranks_to_save.items()
    }

    logger.info('Saving results..')

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
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

            # log example rank
            mlflow.log_artifact(df_filename, 'fresh_ranking_results')

    logger.info('Done.')


@baker.command
def evaluate_fresh(fresh_ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                   checkpoint_path,  # path to the model checkpoint to load
                   # network to use between 'mtje', 'mtje_cosine',
                   # 'mtje_pairwise_distance' and 'aloha'
                   net_type='mtje',
                   min_n_anchor_samples=1,  # minimum number of anchor samples to use, per-family
                   max_n_anchor_samples=10,  # maximum number of anchor samples to use, per-family
                   n_query_samples=23,  # number of query samples per-family to consider
                   n_evaluations=15,  # number of evaluations to perform (for uncertainty estimates)
                   batch_size=1000):  # how many samples per batch to load
    """ Evaluate the model on both the family prediction task and on the family ranking task.

    Args:
        fresh_ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'mtje', 'mtje_cosine', 'mtje_pairwise_distance' and 'aloha' (default: 'mtje')
        min_n_anchor_samples: Minimum number of anchor samples to use, per-family (default: 1)
        max_n_anchor_samples: Maximum number of anchor samples to use, per-family (default: 10)
        n_query_samples: Number of query samples per-family to consider (default: 23)
        n_evaluations: Number of evaluations to perform (for uncertainty estimates) (default: 15)
        batch_size: How many samples per batch to load (default: 1000)
    """

    # start mlflow run
    with mlflow.start_run():
        logger.info('Now launching "evaluate_fresh_scores" function..')
        evaluate_fresh_scores(ds_path=fresh_ds_path,
                              checkpoint_path=checkpoint_path,
                              net_type=net_type,
                              n_query_samples=n_query_samples,
                              min_n_anchor_samples=min_n_anchor_samples,
                              max_n_anchor_samples=max_n_anchor_samples,
                              n_evaluations=n_evaluations,
                              batch_size=batch_size)

        logger.info('Now launching "evaluate_fresh_rankings" function..')
        # evaluate model on the family ranking task
        evaluate_fresh_rankings(ds_path=fresh_ds_path,
                                checkpoint_path=checkpoint_path,
                                net_type=net_type,
                                n_query_samples=n_query_samples,
                                n_evaluations=n_evaluations,
                                batch_size=batch_size)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
