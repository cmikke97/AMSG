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
from collections import defaultdict  # dict subclass that calls a factory function to supply missing values
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import psutil  # used for retrieving information on running processes and system utilization
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python
from matplotlib import pyplot as plt  # state-based interface to matplotlib, provides a MATLAB-like way of plotting

from nets.generators.dataset_alt import Dataset
from nets.generators.generators_alt3 import get_generator

# set minimum and maximum chunk_size exponents
MIN_CHUNK_SIZE_EXPONENT = 4
MAX_CHUNK_SIZE_EXPONENT = 14

# set minimum and maximum chunks exponents
MIN_CHUNKS_EXPONENT = 3
MAX_CHUNKS_EXPONENT = 13

# get config file path
model_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file (the section depends on the net type)
device = config['general']['device']


def import_modules(net_type):  # network type
    """ Dynamically import network module depending on the provided argument.

    Args:
        net_type: Network type (possible values: mtje, mtje_cosine,
                  mtje_pairwise_distance, aloha)
    Returns:
        Net, compute_loss, device and run additional parameters imported from selected modules and config file.
    """

    # set network module name based on the current network type
    if net_type.lower() == 'mtje':
        net_type = 'mtje'
        net_module_name = "nets.MTJE_net"
    elif net_type.lower() == 'mtje_cosine':
        net_type = 'mtje'
        net_module_name = "nets.MTJE_net_cosine"
    elif net_type.lower() == 'mtje_pairwise_distance':
        net_type = 'mtje'
        net_module_name = "nets.MTJE_net_pairwise_distance"
    elif net_type.lower() == 'aloha':
        net_type = 'aloha'
        net_module_name = "nets.ALOHA_net"
    else:  # if the network type is neither mtje nor aloha raise ValueError
        raise ValueError('Unknown Network type. Possible values: "mtje", "mtje_cosine", "mtje_pairwise_distance" or'
                         '"aloha". Got {} '.format(net_type))

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

    try:
        # try getting loss weights from config file
        loss_wts = json.loads(config[net_type]['loss_weights'])
    except json.JSONDecodeError:
        # if the option is not present in the config file set loss weights to None
        loss_wts = None

    # instantiate run additional parameters dict setting values got from config file
    run_additional_params = {
        'layer_sizes': layer_sizes,
        'dropout_p': float(config[net_type]['dropout_p']),
        'activation_function': config[net_type]['activation_function'],
        'normalization_function': config[net_type]['normalization_function'],
        'loss_wts': loss_wts,
        'optimizer': config[net_type]['optimizer'],
        'lr': float(config[net_type]['lr']),
        'momentum': float(config[net_type]['momentum']),
        'weight_decay': float(config[net_type]['weight_decay'])
    }

    # return classes, functions and variables imported
    return Net, run_additional_params


def heatmap(data,  # a 2D numpy array of shape (N, M) containing the data to generate heatmap from
            row_labels,  # a list or array of length N with the labels for the rows
            row_title,  # vertical (rows) axis title
            col_labels,  # a list or array of length M with the labels for the columns
            col_title,  # horizontal (columns) axis title
            ax=None,  # a `matplotlib.axes.Axes` instance to which the heatmap is plotted
            cbar_kw=None,  # A dictionary with arguments to `matplotlib.Figure.colorbar`
            cbarlabel="",  # The label for the colorbar. (Optional)
            **kwargs):  # All other arguments are forwarded to `imshow`
    """ Create a heatmap from a numpy array and two lists of labels.

    Args:
        data: A 2D numpy array of shape (N, M) containing the data to generate heatmap from
        row_labels: A list or array of length N with the labels for the rows
        row_title: Vertical (rows) axis title
        col_labels: A list or array of length M with the labels for the columns
        col_title: Horizontal (columns) axis title
        ax: A `matplotlib.axes.Axes` instance to which the heatmap is plotted. If not provided, use current axes
            or create a new one (Optional)
        cbar_kw: A dictionary with arguments to `matplotlib.Figure.colorbar` (Optional)
        cbarlabel: The label for the colorbar (Optional)
        **kwargs: All other arguments are forwarded to `imshow`
    """

    # if the dictionary of arguments for the colorbar is None, initialize it to an empty dict
    if cbar_kw is None:
        cbar_kw = {}
    # create Axes instance on the current figure ax was None
    if not ax:
        ax = plt.gca()

    # plot the heatmap
    im = ax.imshow(data, **kwargs)

    # create the colorbar
    cbar = ax.figure.colorbar(im, ax=ax, **cbar_kw)
    cbar.ax.set_ylabel(cbarlabel, rotation=-90, va="bottom")

    # set axes titles
    ax.set_xlabel(col_title, fontsize='large')
    ax.set_ylabel(row_title, fontsize='large')

    # show all ticks
    ax.set_xticks(np.arange(data.shape[1]))
    ax.set_yticks(np.arange(data.shape[0]))
    # label ticks with the respective list entries
    ax.set_xticklabels(col_labels)
    ax.set_yticklabels(row_labels)

    # let the horizontal axes labeling appear on top
    ax.tick_params(top=True, bottom=False,
                   labeltop=True, labelbottom=False)

    # rotate the tick labels and set their alignment
    plt.setp(ax.get_xticklabels(), rotation=-30, ha="right",
             rotation_mode="anchor")

    # turn spines off and create white grid
    ax.spines[:].set_visible(False)

    # set tick locations
    ax.set_xticks(np.arange(data.shape[1] + 1) - .5, minor=True)
    ax.set_yticks(np.arange(data.shape[0] + 1) - .5, minor=True)
    # configure grid lines
    ax.grid(which="minor", color="w", linestyle='-', linewidth=3)
    # turn off bottom and left ticks
    ax.tick_params(which="minor", bottom=False, left=False)

    # return heatmap and colorbar
    return im, cbar


def annotate_heatmap(im,  # the AxesImage to be labeled
                     # a 2D numpy array of shape (N, M) containing the standard deviations to be used to annotate
                     # the heatmap
                     std,
                     # a 2D python array containing Boolean values indicating whether each single cell contains
                     # data or not
                     mask,
                     # the format of the annotations inside the heatmap.  This should be either 'time' or 'speed'
                     ann_format='time',
                     # a pair of colors.  The first is used for values below a threshold, the second for those above
                     textcolors=("black", "white"),
                     # value in data units according to which the colors from textcolors are applied.
                     # If None (the default) uses the middle of the colormap as separation
                     threshold=None,
                     # all other arguments are forwarded to each call to `text` used to create the text labels
                     **textkw):
    """ A function to annotate a heatmap.

    Args:
        im: The AxesImage to be labeled
        std: A 2D numpy array of shape (N, M) containing the standard deviations to be used to annotate the heatmap
        mask: A 2D python array containing Boolean values indicating whether each single cell contains data or not
        ann_format: The format of the annotations inside the heatmap.  This should be either 'time' or 'speed'
        textcolors: A pair of colors.  The first is used for values below a threshold, the second for those above
        threshold: Value in data units according to which the colors from textcolors are applied.
                   If None (the default) uses the middle of the colormap as separation
        **textkw: All other arguments are forwarded to each call to `text` used to create the text labels
    """

    # get data from 'im' AxesImage
    data = im.get_array()

    # normalize the threshold to the images color range
    if threshold is not None:
        threshold = im.norm(threshold)
    else:  # if threshold was not provided set threshold using the middle of the colormap as separation
        threshold = im.norm(data.max()) / 2.

    # Set default alignment to center, but allow it to be overwritten by textkw.
    kw = dict(horizontalalignment="center",
              verticalalignment="center")
    kw.update(textkw)

    # if the annotation is not of type 'time' nor 'speed', raise error
    if ann_format != 'time' and ann_format != 'speed':
        raise ValueError('Unknown format type.')

    # initialize texts list to be empty
    texts = []

    # loop over the data
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if mask[i][j]:  # skip data point if its mask value is true
                continue

            # update color depending on the current data point
            kw.update(color=textcolors[int(im.norm(data[i, j]) > threshold)])

            if ann_format == 'time':  # if the annotation is of type 'time'
                # create text of type 'time' for the current data point
                text = im.axes.text(j, i, '{}\n+/-{:4.0f}s'
                                    .format(time.strftime("%H:%M:%S",
                                                          time.gmtime(float(data[i, j]))), std[i, j]), **kw)
            else:  # if the annotation is of type 'speed'
                # create text of type 'speed' for the current data point
                text = im.axes.text(j, i, '{:6.3f}it/s\n+/-\n{:6.3f}it/s'.format(data[i, j],
                                                                                 std[i, j]), **kw)

            # append generated text to texts list
            texts.append(text)

    return texts


@baker.command
def gen3_eval(ds_path,  # path of the directory where to find the pre-processed dataset (containing .dat files)
              # path to a new or an existent (from a previous run) json file to be used to store run
              # evaluation elapsed times and speeds
              json_file_path,
              net_type='mtje',  # network to use
              batch_size=8192,  # how many samples per batch to load
              min_mul=1,  # minimum product between chunks and chunk_size to consider (in # of batches)
              max_mul=32,  # maximum product between chunks and chunk_size to consider (in # of batches)
              epochs=1,  # number of epochs to perform evaluation for
              training_n_samples=0,  # number of training samples to consider (used to access the right files)
              use_malicious_labels=1,  # whether or not (1/0) to use malware/benignware labels as a target
              use_count_labels=1,  # whether or not (1/0) to use the counts as an additional target
              use_tag_labels=1,  # whether or not (1/0) to use the tags as additional targets
              feature_dimension=2381,  # The input dimension of the model
              # if provided, seed random number generation with this value (defaults None, no seeding)
              random_seed=None,
              # how many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())
              workers=0):
    """ Evaluate generator alt3 speed changing values for 'chunk_size' and 'chunks' variables. The evaluation is done
    for 'epochs' epochs for each combination of values. The resulting elapsed times and speeds are save to a json file.

    Args:
        ds_path: Path of the directory where to find the pre-processed dataset (containing .dat files)
        json_file_path: Path to a new or an existent (from a previous run) json file to be used to store run
                        evaluation elapsed times and speeds
        net_type: Network to use between 'mtje', 'mtje_cosine', 'mtje_pairwise_distance' and 'aloha'. (default: 'mtje')
        batch_size: How many samples per batch to load. (default: 8192)
        min_mul: Minimum product between chunks and chunk_size to consider (in # of batches). (default: 1)
        max_mul: Maximum product between chunks and chunk_size to consider (in # of batches). (default: 32)
        epochs: How many epochs to train for. (default: 1)
        training_n_samples: Number of training samples to consider (used to access the right files).
                            (default: 0 -> all)
        use_malicious_labels: Whether or (1/0) not to use malware/benignware labels as a target. (default: 1)
        use_count_labels: Whether or not (1/0) to use the counts as an additional target. (default: 1)
        use_tag_labels: Whether or not (1/0) to use the tags as additional targets. (default: 1)
        feature_dimension: The input dimension of the model. (default: 2381 -> EMBER 2.0 feature size)
        random_seed: If provided, seed random number generation with this value. (default: None -> no seeding)
        workers: How many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())
    """

    # dynamically import some classes, functions and variables from modules depending on the current net type
    Net, run_additional_params = import_modules(net_type=net_type)

    # start mlflow run
    with mlflow.start_run() as mlrun:
        if net_type.lower() != 'aloha':
            # joint embedding nets have use_tag_labels set to 1 by default
            use_tag_labels = 1

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('Running generator alternative 3 cross evaluation..')

        # initialize chunk_sizes and chunks lists to contain all the powers of 2 between
        # 2^MIN_EXPONENT and 2^MAX_EXPONENT (included)
        chunk_sizes_iterator = [2 ** x for x in range(MIN_CHUNK_SIZE_EXPONENT, MAX_CHUNK_SIZE_EXPONENT + 1)]
        chunks_iterator = [2 ** x for x in range(MIN_CHUNKS_EXPONENT, MAX_CHUNKS_EXPONENT + 1)]

        # create json file parent directory if it did not already exist
        os.makedirs(os.path.dirname(json_file_path), exist_ok=True)

        # if the json file path provided points to an existing file, open it and load its content into data dict
        if os.path.exists(json_file_path) and os.path.isfile(json_file_path):
            with open(json_file_path, 'r') as f:
                data = json.load(f)
        else:  # otherwise initialize data dict to contain two vectors (elapsed_times and speeds) containing None values
            data = {
                'elapsed_times': {str(cs): {str(c): None for c in chunks_iterator} for cs in chunk_sizes_iterator},
                'speeds': {str(cs): {str(c): None for c in chunks_iterator} for cs in chunk_sizes_iterator}
            }

        # for each chunk size
        for cs in chunk_sizes_iterator:
            # for each chunk number
            for c in chunks_iterator:

                # if the product between current chunk size and number of chunks is outside the valid range,
                # skip evaluation
                if cs * c < batch_size * min_mul or cs * c > batch_size * max_mul:
                    continue

                # if the values in the data dict corresponding to the current combination of chunk size and chunks
                # number are None, initialize then to empty vectors
                if data['elapsed_times'][str(cs)][str(c)] is None or data['speeds'][str(cs)][str(c)] is None:
                    data['elapsed_times'][str(cs)][str(c)] = []
                    data['speeds'][str(cs)][str(c)] = []

                # create Network model
                model = Net(use_malware=bool(use_malicious_labels),
                            use_counts=bool(use_count_labels),
                            use_tags=bool(use_tag_labels),
                            n_tags=len(Dataset.tags),
                            feature_dimension=feature_dimension,
                            layer_sizes=run_additional_params['layer_sizes'],
                            dropout_p=run_additional_params['dropout_p'],
                            activation_function=run_additional_params['activation_function'],
                            normalization_function=run_additional_params['normalization_function'])

                # select optimizer is selected given the run additional parameters got from config file
                # if adam optimizer is selected
                if run_additional_params['optimizer'].lower() == 'adam':
                    # use Adam optimizer on all the model parameters
                    opt = torch.optim.Adam(model.parameters(),
                                           lr=run_additional_params['lr'],
                                           weight_decay=run_additional_params['weight_decay'])
                # else if sgd optimizer is selected
                elif run_additional_params['optimizer'].lower() == 'sgd':
                    # use stochastic gradient descent on all the model parameters
                    opt = torch.optim.SGD(model.parameters(),
                                          lr=run_additional_params['lr'],
                                          weight_decay=run_additional_params['weight_decay'],
                                          momentum=run_additional_params['momentum'])
                else:  # otherwise raise error
                    raise ValueError(
                        'Unknown optimizer {}. Try "adam" or "sgd".'.format(run_additional_params['optimizer']))

                # create train generator (a.k.a. Dataloader)
                generator = get_generator(ds_root=ds_path,
                                          batch_size=batch_size,
                                          chunk_size=cs,
                                          chunks=c,
                                          mode='train',
                                          num_workers=workers,
                                          n_samples=training_n_samples,
                                          use_malicious_labels=bool(use_malicious_labels),
                                          use_count_labels=bool(use_count_labels),
                                          use_tag_labels=bool(use_tag_labels))

                # get number of steps per epoch (# of total batches) from generator
                steps_per_epoch = len(generator)

                # allocate model to selected device
                model.to(device)

                # instantiate a new dictionary-like object called loss_histories
                loss_histories = defaultdict(list)
                # set the model mode to 'train'
                model.train()

                # initialize current elapsed times and speeds vectors with zeroes
                current_elapsed_times = [0.0 for _ in range(epochs)]
                current_speeds = [0.0 for _ in range(epochs)]

                # loop for the selected number of epochs
                for epoch in range(epochs):

                    # set current epoch start time
                    start_time = time.time()

                    # for all the training batches
                    for i, (features, labels) in enumerate(generator):
                        opt.zero_grad()  # clear old gradients from the last step

                        # copy current features and allocate them on the selected device (CPU or GPU)
                        features = deepcopy(features).to(device)

                        # perform a forward pass through the network
                        out = model(features)

                        # compute loss given the predicted output from the model
                        loss_dict = model.compute_loss(out,
                                                       deepcopy(labels),
                                                       loss_wts=run_additional_params['loss_wts'])

                        # extract total loss
                        loss = loss_dict['total']

                        # compute gradients
                        loss.backward()

                        # update model parameters
                        opt.step()

                        # for all the calculated losses in loss_dict
                        for k in loss_dict.keys():
                            # if the loss is 'total' then append it to loss_histories['total'] after having detached it
                            # and passed it to the cpu
                            if k == 'total':
                                loss_histories[k].append(deepcopy(loss_dict[k].detach().cpu().item()))
                            # otherwise append the loss to loss_histories without having to detach it
                            else:
                                loss_histories[k].append(loss_dict[k])

                        # compute current epoch elapsed time (in seconds)
                        elapsed_time = time.time() - start_time

                        # create loss string with the current losses
                        loss_str = " ".join([f"{key} loss:{value:7.3f}" for key, value in loss_dict.items()])
                        loss_str += " | "
                        loss_str += " ".join(
                            [f"{key} mean:{np.mean(value):7.3f}" for key, value in loss_histories.items()])

                        # write on standard out the loss string + other information (elapsed time,
                        # predicted total epoch completion time, current mean speed and main memory usage)
                        sys.stdout.write('\r Epoch: {}/{} {}/{} '.format(epoch + 1, epochs, i + 1, steps_per_epoch)
                                         + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%, chunk_size: {}, chunks: {}] '
                                         .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # elapsed time
                                                 time.strftime("%H:%M:%S",  # predict total epoch completion time
                                                               time.gmtime(steps_per_epoch * elapsed_time / (i + 1))),
                                                 (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                                 psutil.virtual_memory().percent,  # get percentage of main memory used
                                                 cs,  # chunk size
                                                 c)  # chunks number
                                         + loss_str)  # append loss string

                        # flush standard output
                        sys.stdout.flush()
                        del features, labels  # to avoid weird references that lead to generator errors

                    print()

                    # save final elapsed time and speed for the current epoch
                    current_elapsed_times[epoch] = elapsed_time
                    current_speeds[epoch] = steps_per_epoch / elapsed_time

                # save current chunk size - chunks combination elapsed times and speeds extending the lists
                data['elapsed_times'][str(cs)][str(c)].extend(current_elapsed_times)
                data['speeds'][str(cs)][str(c)].extend(current_speeds)

        # save content of data dict to json file
        with open(json_file_path, 'w') as f:
            json.dump(data, f)

        logger.info('...done')


@baker.command
def create_gen3_heatmap(json_file_path):
    """ Create elapsed time and speed heatmaps from a json file resulting from 'gen3_eval', which contains the times
    elapsed and speeds for a number of evaluation runs.

    Args:
        json_file_path: Path the json file containing the run evaluation elapsed times and speeds
    """

    # start mlflow run
    with mlflow.start_run() as mlrun:
        # if the json file does not exist, raise error
        if not os.path.exists(json_file_path) or not os.path.isfile(json_file_path):
            raise ValueError('{} does not exist'.format(json_file_path))

        # initialize chunk_sizes and chunks lists to contain all the powers of 2 between
        # 2^MIN_EXPONENT and 2^MAX_EXPONENT (included)
        chunk_sizes_iterator = [2 ** x for x in range(MIN_CHUNK_SIZE_EXPONENT, MAX_CHUNK_SIZE_EXPONENT + 1)]
        chunks_iterator = [2 ** x for x in range(MIN_CHUNKS_EXPONENT, MAX_CHUNKS_EXPONENT + 1)]

        # open json file and load its content in the data dict
        with open(json_file_path, 'r') as f:
            data = json.load(f)

            # instantiate empty numpy arrays for containing the average values and standard deviations for
            # both elapsed times and speeds
            elapsed_times_avg = np.empty(shape=(len(chunk_sizes_iterator), len(chunks_iterator)), dtype=np.float32)
            speeds_avg = np.empty(shape=(len(chunk_sizes_iterator), len(chunks_iterator)), dtype=np.float32)
            elapsed_times_std = np.empty(shape=(len(chunk_sizes_iterator), len(chunks_iterator)), dtype=np.float32)
            speeds_std = np.empty(shape=(len(chunk_sizes_iterator), len(chunks_iterator)), dtype=np.float32)

            # assign NaN (Not a Number) value to all positions of the numpy arrays just defined
            # (NaN will be ignored when plotting the heatmap)
            elapsed_times_avg[:] = np.NaN
            speeds_avg[:] = np.NaN
            elapsed_times_std[:] = np.NaN
            speeds_std[:] = np.NaN

            # for each chunk size
            for i, cs in enumerate(chunk_sizes_iterator):
                # for each chunks number
                for j, c in enumerate(chunks_iterator):
                    # if the value in data dict corresponding to the combination of chunk size and chunks number is None
                    # for speeds or times, continue to next combination
                    if data['elapsed_times'][str(cs)][str(c)] is None or data['speeds'][str(cs)][str(c)] is None:
                        continue

                    # compute average values and standard deviations for the elapsed times and speeds
                    elapsed_times_avg[i][j] = np.average(data['elapsed_times'][str(cs)][str(c)])
                    elapsed_times_std[i][j] = np.std(data['elapsed_times'][str(cs)][str(c)])
                    speeds_avg[i][j] = np.average(data['speeds'][str(cs)][str(c)])
                    speeds_std[i][j] = np.std(data['speeds'][str(cs)][str(c)])

            # create elapsed times and speeds figures
            time_fig, time_ax = plt.subplots(figsize=(10, 9))
            speed_fig, speed_ax = plt.subplots(figsize=(10, 9))

            # compute elapsed times heatmap
            time_im, time_cbar = heatmap(elapsed_times_avg,
                                         row_labels=chunk_sizes_iterator,
                                         row_title='Chunk sizes',
                                         col_labels=chunks_iterator,
                                         col_title='Chunks',
                                         ax=time_ax,
                                         cmap="BuGn",
                                         cbarlabel="elapsed time [s]")

            # compute speeds heatmap
            speed_im, speed_cbar = heatmap(speeds_avg,
                                           row_labels=chunk_sizes_iterator,
                                           row_title='Chunk sizes',
                                           col_labels=chunks_iterator,
                                           col_title='Chunks',
                                           ax=speed_ax,
                                           cmap="BuGn",
                                           cbarlabel="speed [it/s]")

            # compute elapsed times and speeds masks
            time_mask = [[np.isnan(c) for c in cs] for cs in elapsed_times_avg]
            speed_mask = [[np.isnan(c) for c in cs] for cs in speeds_avg]

            # annotate elapsed times and speeds heatmaps give the corresponding masks
            time_texts = annotate_heatmap(time_im,
                                          elapsed_times_std,
                                          time_mask,
                                          ann_format='time',
                                          fontsize='x-small')
            speed_texts = annotate_heatmap(speed_im,
                                           speeds_std,
                                           speed_mask,
                                           ann_format='speed',
                                           fontsize='x-small')

            # adjusts subplots params so that the subplot fits in to the figure area
            time_fig.tight_layout()
            speed_fig.tight_layout()

            # create temporary directory
            with tempfile.TemporaryDirectory() as tmpdir:
                # save both elapsed times and speeds heatmaps to temporary files
                time_filename = os.path.join(tmpdir, 'times.png')
                speed_filename = os.path.join(tmpdir, 'speeds.png')
                time_fig.savefig(time_filename)
                speed_fig.savefig(speed_filename)

                # log temporary files as artifacts
                mlflow.log_artifact(time_filename)
                mlflow.log_artifact(speed_filename)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
