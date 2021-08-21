import configparser  # implements a basic configuration language for Python programs
import importlib  # provides the implementation of the import statement in Python source code
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
import time
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
import psutil
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python
from tqdm import tqdm

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
        a: Inversion multiplication factor
        function: Inversion function to use. Possible values are: 'exp', 'inv' or 'inv_pow'
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


# network type (possible values: jointEmbedding, JointEmbedding_cosine, JointEmbedding_pairwise_distance, detectionBase)
def import_modules(net_type):
    """ Dynamically import network depending on the provided argument.

    Args:
        net_type: Network type (possible values: jointEmbedding, JointEmbedding_cosine,
                  JointEmbedding_pairwise_distance, detectionBase)
    Returns:
        Net imported from selected modules.
    """

    # set network module name based on the current network type
    if net_type.lower() == 'jointembedding':
        net_type = 'jointEmbedding'
        net_module_name = 'nets.JointEmbedding_net'
        similarity_type = 'dotProduct'
    elif net_type.lower() == 'jointembedding_cosine':
        net_type = 'jointEmbedding'
        net_module_name = 'nets.JointEmbedding_net_cosine'
        similarity_type = 'cosineSimilarity'
    elif net_type.lower() == 'jointembedding_pairwise_distance':
        net_type = 'jointEmbedding'
        net_module_name = 'nets.JointEmbedding_net_pairwise_distance'
        similarity_type = 'invertedEuclideanDistance'
    elif net_type.lower() == 'detectionbase':
        net_type = 'detectionBase'
        net_module_name = "nets.DetectionBase_net"
        similarity_type = 'dotProduct'
    else:  # if the network type is neither JointEmbedding nor DetectionBase raise ValueError
        raise ValueError('Unknown Network type. Possible values: "JointEmbedding", "jointEmbedding_cosine" or '
                         '"jointEmbedding_pairwise_distance". Got {} '
                         .format(net_type))

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
    samples = None
    samples_families = [0 for _ in range(n_families)]

    # for all the batches in the generator (Dataloader)
    for shas, features, labels in generator:
        if other is not None:
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
                          # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                          # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                          net_type='JointEmbedding',
                          n_query_samples=23,  # number of query samples to retrieve, per-family
                          min_n_anchor_samples=1,  # minimum number of anchor samples to use, per-family
                          max_n_anchor_samples=10,  # maximum number of anchor samples to use, per-family
                          n_evaluations=15,  # number of evaluations to perform (for uncertainty estimates)
                          batch_size=1000):  # how many samples per batch to load

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

    is_aloha_run = net_type.lower() == 'detectionbase'

    # if the total number of anchor samples is greater than the dataset size, error
    if max_n_anchor_samples * n_families >= generator.dataset.__len__():
        raise ValueError('The selected maximum number of anchor samples is too high. -> max_n_anchor_samples ({}) x '
                         'num_families ({}) = {} > dataset size ({}).'.format(max_n_anchor_samples,
                                                                              n_families,
                                                                              max_n_anchor_samples * n_families,
                                                                              generator.dataset.__len__()))

    if min_n_anchor_samples <= 0:
        raise ValueError('Minimum number of anchor samples must be a positive integer. Found {}.'.format(
            min_n_anchor_samples))

    if n_query_samples <= 0:
        raise ValueError('Number of query samples must be a positive integer. Found: {}.'.format(
            n_query_samples))

    predictions = {}
    f_predictions = {}
    for k, n_anchor_samples in enumerate(range(min_n_anchor_samples, max_n_anchor_samples + 1)):
        predictions[str(n_anchor_samples)] = []
        f_predictions[str(n_anchor_samples)] = []

        # set current epoch start time
        start_time = time.time()

        for j in range(n_evaluations):
            anchors = get_samples(model, generator, n_families, n_anchor_samples)
            queries = get_samples(model, generator, n_families, n_query_samples, other=anchors)

            if is_aloha_run:
                f_similarity_scores = torch.matmul(queries['features'], anchors['features'].T).cpu().detach()
                similarity_scores = torch.matmul(queries['embeddings'], anchors['embeddings'].T).cpu().detach()
            else:
                f_similarity_scores = []
                # compute the similarity scores between the samples and anchors' embeddings using the model's
                # get_similarity function
                similarity_scores = model.get_similarity(queries['embeddings'],
                                                         anchors['embeddings'])['similarity'].cpu().detach()

            shas = queries['shas']
            labels = queries['labels']

            curr_predictions = anchors['labels'][torch.argmax(similarity_scores, dim=1)]
            curr_probabilities = torch.nn.Softmax(dim=1)(torch.tensor([[torch.max(
                sims[[j for j in range(len(sims)) if anchors['labels'][j] == i]]).item() for i in range(n_families)] for
                                                                  sims in similarity_scores]))

            predictions[str(n_anchor_samples)].append({
                'families': [label_to_sig(lab) for lab in range(n_families)],
                'shas': shas,
                'labels': labels.tolist(),
                'predictions': curr_predictions.tolist(),
                'probabilities': curr_probabilities.tolist()
            })

            if is_aloha_run:
                curr_f_predictions = anchors['labels'][torch.argmax(f_similarity_scores, dim=1)]
                curr_f_probabilities = torch.nn.Sigmoid()(torch.tensor([[torch.max(
                    sims[[j for j in range(len(sims)) if anchors['labels'][j] == i]]).item() for i in range(n_families)]
                                                                        for sims in f_similarity_scores]))

                f_predictions[str(n_anchor_samples)].append({
                    'families': [label_to_sig(lab) for lab in range(n_families)],
                    'shas': shas,
                    'labels': labels.tolist(),
                    'predictions': curr_f_predictions.tolist(),
                    'probabilities': curr_f_probabilities.tolist()
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

    with tempfile.TemporaryDirectory() as tmpdir:
        predictions_result_json_path = os.path.join(tmpdir, 'fresh_prediction_results.json')

        with open(predictions_result_json_path, 'w') as outfile:
            json.dump(predictions, outfile)

        mlflow.log_artifact(predictions_result_json_path, 'fresh_prediction_results')

        if is_aloha_run:
            f_predictions_result_json_path = os.path.join(tmpdir, 'fresh_features_prediction_results.json')

            with open(f_predictions_result_json_path, 'w') as outfile:
                json.dump(f_predictions, outfile)

            mlflow.log_artifact(f_predictions_result_json_path, 'fresh_prediction_results')


def compute_ranking_scores(ranking_scores,
                           global_ranks_to_save,
                           rank_per_query):
    # compute binarized (0/1) relevance scores
    rs = [np.asarray([i == rank['ground_truth_label'] for i in rank['rank_labels']], dtype=np.dtype(int))
          for rank in rank_per_query]

    # compute and log MRR and MAP scores
    ranking_scores['MRR'].append(mean_reciprocal_rank(rs))
    ranking_scores['MAP'].append(mean_average_precision(rs))

    max_rr, max_rr_idx = max_reciprocal_rank(rs)
    min_rr, min_rr_idx = min_reciprocal_rank(rs)
    max_ap, max_ap_idx = max_average_precision(rs)
    min_ap, min_ap_idx = min_average_precision(rs)

    # compute a bunch of indexes for interesting queries to save in csv files as examples
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

    if global_ranks_to_save is None:
        global_ranks_to_save = ranks_to_save
    else:
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

    return ranking_scores, global_ranks_to_save, rank_per_query


def evaluate_fresh_rankings(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                            checkpoint_path,  # path to the model checkpoint to load
                            # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                            # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                            net_type='JointEmbedding',
                            n_query_samples=23,  # number of query samples per-family to consider
                            n_evaluations=15,  # number of evaluations to perform (for uncertainty estimates)
                            batch_size=1000):  # how many samples per batch to load
    """ Take a trained feedforward neural network model and output fresh dataset evaluation results to a csv file.

    Args:
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance'
                  and 'DetectionBase'. (default: 'JointEmbedding')
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

    is_aloha_run = net_type.lower() == 'detectionbase'

    # if the total number of anchor samples is greater than the dataset size, error
    if n_query_samples * n_families >= generator.dataset.__len__():
        raise ValueError('The selected maximum number of query samples is too high. -> n_query_samples ({}) x '
                         'num_families ({}) = {} > dataset size ({}).'.format(n_query_samples,
                                                                              n_families,
                                                                              n_query_samples * n_families,
                                                                              generator.dataset.__len__()))

    ranking_scores = {'MRR': [], 'MAP': []}
    f_ranking_scores = {'MRR': [], 'MAP': []}
    global_ranks_to_save = None
    f_global_ranks_to_save = None

    # set current epoch start time
    start_time = time.time()
    for j in range(n_evaluations):
        # set queries and rank_per_query dicts to null value
        queries = get_samples(model, generator, n_families, n_query_samples)

        rank_per_query = []
        f_rank_per_query = []
        # for all the batches in the generator (Dataloader)
        for shas, features, labels in generator:
            # transfer features to selected device
            features = features.to(device)

            # perform a forward pass through the network and get predictions
            predictions = model.get_embedding(features)

            # get embeddings
            embeddings = predictions['embedding']

            if is_aloha_run:
                f_similarity_scores = torch.matmul(queries['features'], features.T).cpu().detach()
                similarity_scores = torch.matmul(queries['embeddings'], embeddings.T).cpu().detach()
            else:
                f_similarity_scores = []
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

                if is_aloha_run:
                    indices = -similarity_scores[i, [j for j in range(len(f_similarity_scores[i]))
                                                     if shas[j] != s]].argsort()

                    f_rank_per_query.append({
                        'query_sha': s,
                        'ground_truth_label': int(queries['labels'][i].item()),
                        'ground_truth_family': label_to_sig(int(queries['labels'][i].item())),
                        'rank_shas': np.asarray(shas, dtype=np.dtype('U64'))[indices].tolist(),
                        'rank_labels': [int(lab) for lab in labels[indices]],
                        'rank_families': [label_to_sig(int(lab.item())) for lab in labels[indices]]
                    })

        ranking_scores, global_ranks_to_save, rank_per_query = compute_ranking_scores(ranking_scores,
                                                                                      global_ranks_to_save,
                                                                                      rank_per_query)

        if is_aloha_run:
            f_ranking_scores, f_global_ranks_to_save, f_rank_per_query = compute_ranking_scores(f_ranking_scores,
                                                                                                f_global_ranks_to_save,
                                                                                                f_rank_per_query)

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

    f_dataframes = {}
    f_metadata = {}
    if is_aloha_run:
        mlflow.log_metric('features_MRR_mean', float(np.mean(f_ranking_scores['MRR'])))
        mlflow.log_metric('features_MRR_std', float(np.std(f_ranking_scores['MRR'])))
        mlflow.log_metric('features_MAP_mean', float(np.mean(f_ranking_scores['MAP'])))
        mlflow.log_metric('features_MAP_std', float(np.std(f_ranking_scores['MAP'])))

        # compute example ranks dataframes
        f_dataframes = {
            key: pd.DataFrame({"sha256": value['rank']['rank_shas'],
                               "label": value['rank']['rank_labels'],
                               "family": value['rank']['rank_families']})
            for key, value in f_global_ranks_to_save.items()
        }

        # compute example ranks metadata
        f_metadata = {
            key: pd.Series([
                '{}: {}'.format(key, value['value']),
                'Query sample sha256: {}'.format(value['rank']['query_sha']),
                'Ground truth label: {}'.format(value['rank']['ground_truth_label']),
                'Ground truth family: {}'.format(value['rank']['ground_truth_family'])
            ])
            for key, value in f_global_ranks_to_save.items()
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

        if is_aloha_run:
            # for each example rank
            for df_key, df_val in f_dataframes.items():
                # retrieve metadata
                meta = f_metadata[df_key]

                # create file name
                df_filename = os.path.join(tempdir, '{}_example_fresh_rank.csv'.format(df_key))

                # open dataframe dest file and write both metadata and dataframe to it
                with open(df_filename, 'w') as df_f:
                    meta.to_csv(df_f, index=False)
                    df_val.to_csv(df_f)

                # log example rank
                mlflow.log_artifact(df_filename, 'fresh_ranking_results')

    logger.info('Done.')


def normalize_tag_results(labels,  # labels (ground truth)
                          results_dict):  # results (predicted labels) dictionary
    """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
    that pandas can convert to a DataFrame.
    Args:
        labels: Labels (ground truth)
        results_dict: Results (predicted labels) dictionary
    Returns:
        Dictionary containing labels and predictions.
    """

    # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
    # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

    rv = {'family_label': detach_and_copy_array(labels[:])}  # initialize return value dict

    for column, tag in enumerate(all_tags):  # for all the tags
        # normalize predicted tag array and save it into rv
        rv['pred_{}_tag'.format(tag)] = detach_and_copy_array(results_dict['probability'][:, column])

    return rv


@baker.command
def predict_tags(fresh_ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                 checkpoint_file,  # the checkpoint file containing the weights to evaluate
                 # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                 # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                 net_type='JointEmbedding',
                 batch_size=250,  # how many samples per batch to load
                 feature_dimension=2381):  # the input dimension of the model
    """ Take a trained feedforward neural network model and output evaluation results to a csv file.
    Args:
        fresh_ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_file: The checkpoint file containing the weights to evaluate
        net_type: Network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance'
                  and 'DetectionBase'. (default: 'JointEmbedding')
        batch_size: How many samples per batch to load
        feature_dimension: The input dimension of the model
    """

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net, run_additional_params = import_modules(net_type=net_type)

    # create malware-NN model
    model = Net(use_malware=False,
                use_counts=False,
                use_tags=True,
                n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                feature_dimension=feature_dimension,
                layer_sizes=run_additional_params['layer_sizes'],
                dropout_p=run_additional_params['dropout_p'],
                activation_function=run_additional_params['activation_function'],
                normalization_function=run_additional_params['normalization_function'])

    # load model parameters from checkpoint
    model.load_state_dict(torch.load(checkpoint_file))

    # allocate model to selected device (CPU or GPU)
    model.to(device)

    # set the model mode to 'eval'
    model.eval()

    # create fresh dataset generator
    generator = get_generator(ds_root=fresh_ds_path,
                              batch_size=batch_size,
                              return_shas=True,
                              shuffle=True)  # shuffle samples

    logger.info('...predicting tags for fresh dataset samples')

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        filename = os.path.join(tempdir, 'predicted_tags.csv')

        # create and open the results file in write mode
        with open(filename, 'w') as f:
            first_batch = True
            # for all the batches in the generator (Dataloader)
            for shas, features, labels in tqdm(generator):
                features = features.to(device)  # transfer features to selected device

                # perform a forward pass through the network and get predictions
                predictions = model(features)

                # normalize the results
                results = normalize_tag_results(labels,
                                                predictions)

                # store results into a pandas dataframe (indexed by the sha265 keys) and then save it as csv into
                # file f (inserting the header only if this is the first batch in the loop)
                pd.DataFrame(results, index=shas).to_csv(f, header=first_batch)

                first_batch = False

        # log results file as artifact
        mlflow.log_artifact(filename, artifact_path="fresh_dataset_results")

    logger.info('...done')


@baker.command
def evaluate_fresh(fresh_ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                   checkpoint_path,  # path to the model checkpoint to load
                   # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                   # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                   net_type='JointEmbedding',
                   min_n_anchor_samples=1,  # minimum number of anchor samples to use, per-family
                   max_n_anchor_samples=10,  # maximum number of anchor samples to use, per-family
                   n_query_samples=23,  # number of query samples per-family to consider
                   n_evaluations=15,  # number of evaluations to perform (for uncertainty estimates)
                   batch_size=1000):  # how many samples per batch to load
    """ Evaluate the model on both the family prediction task and on the family ranking task.

    Args:
        fresh_ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                    'JointEmbedding_pairwise_distance' and 'DetectionBase'  (default: 'JointEmbedding')
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

        logger.info('Now launching "predict_tags" function..')
        # predict SMART tags for the fresh dataset samples
        predict_tags(fresh_ds_path=fresh_ds_path,
                     checkpoint_file=checkpoint_path,
                     net_type=net_type)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
