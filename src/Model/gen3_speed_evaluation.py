import configparser  # implements a basic configuration language for Python programs
import importlib  # provides the implementation of the import statement in Python source code
import os  # provides a portable way of using operating system dependent functionality
import shutil  # used to recursively copy an entire directory tree rooted at src to a directory named dst
import sys  # system-specific parameters and functions
from collections import defaultdict  # dict subclass that calls a factory function to supply missing values
from copy import deepcopy  # creates a new object and recursively copies the original object elements
from urllib import parse  # standard interface to break Uniform Resource Locator (URL) in components
import time

import tempfile  # used to create temporary files and directories
import matplotlib
import mlflow
import baker  # easy, powerful access to Python functions from the command line
import numpy as np  # the fundamental package for scientific computing with Python
import psutil
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python
from matplotlib import pyplot as plt

from nets.generators.dataset_alt import Dataset
from nets.generators.generators_alt3 import get_generator


MAX_LIMIT = 2 ** 18


def import_modules(net_type):  # network type (possible values: jointEmbedding, detectionBase)
    """ Dynamically import network module depending on the provided argument.

    Args:
        net_type: Network type (possible values: jointEmbedding, detectionBase)
    Returns:
        Net, compute_loss and device imported from selected modules.
    """

    # set network module name based on the current network type
    if net_type.lower() == 'jointembedding':
        net_type = 'jointEmbedding'
        net_module_name = "nets.JointEmbedding_net"
    elif net_type.lower() == 'detectionbase':
        net_type = 'detectionBase'
        net_module_name = "nets.DetectionBase_net"
    else:  # if the network type is neither JointEmbedding nor DetectionBase raise ValueError
        raise ValueError('Unknown Network type. Possible values: "JointEmbedding", "DetectionBase". Got {}'
                         .format(net_type))

    # import net module
    net_module = importlib.import_module(net_module_name)
    # get 'Net' class from net module
    Net = getattr(net_module, 'Net')
    # get 'compute_loss' function from net module
    compute_loss = getattr(net_module, 'compute_loss')

    # get config file path
    model_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(model_dir)
    config_filepath = os.path.join(src_dir, 'config.ini')

    # instantiate config parser and read config file
    config = configparser.ConfigParser()
    config.read(config_filepath)

    # get variables from config file (the section depends on the net type)
    device = config[net_type]['device']

    # return classes, functions and variables imported
    return Net, compute_loss, device


def heatmap(data, row_labels, col_labels, ax=None,
            cbar_kw=None, cbarlabel="", **kwargs):
    """
    Create a heatmap from a numpy array and two lists of labels.

    Parameters
    ----------
    data
        A 2D numpy array of shape (N, M).
    row_labels
        A list or array of length N with the labels for the rows.
    col_labels
        A list or array of length M with the labels for the columns.
    ax
        A `matplotlib.axes.Axes` instance to which the heatmap is plotted.  If
        not provided, use current axes or create a new one.  Optional.
    cbar_kw
        A dictionary with arguments to `matplotlib.Figure.colorbar`.  Optional.
    cbarlabel
        The label for the colorbar.  Optional.
    **kwargs
        All other arguments are forwarded to `imshow`.
    """

    if cbar_kw is None:
        cbar_kw = {}
    if not ax:
        ax = plt.gca()

    # Plot the heatmap
    im = ax.imshow(data, **kwargs)

    # Create colorbar
    cbar = ax.figure.colorbar(im, ax=ax, **cbar_kw)
    cbar.ax.set_ylabel(cbarlabel, rotation=-90, va="bottom")

    ax.set_xlabel('this')
    ax.set_ylabel('that')

    # We want to show all ticks...
    ax.set_xticks(np.arange(data.shape[1]))
    ax.set_yticks(np.arange(data.shape[0]))
    # ... and label them with the respective list entries.
    ax.set_xticklabels(col_labels)
    ax.set_yticklabels(row_labels)

    # Let the horizontal axes labeling appear on top.
    ax.tick_params(top=True, bottom=False,
                   labeltop=True, labelbottom=False)

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=-30, ha="right",
             rotation_mode="anchor")

    # Turn spines off and create white grid.
    ax.spines[:].set_visible(False)

    ax.set_xticks(np.arange(data.shape[1]+1)-.5, minor=True)
    ax.set_yticks(np.arange(data.shape[0]+1)-.5, minor=True)
    ax.grid(which="minor", color="w", linestyle='-', linewidth=3)
    ax.tick_params(which="minor", bottom=False, left=False)

    return im, cbar


def annotate_heatmap(im, ann_format='time',
                     textcolors=("black", "white"),
                     threshold=None, **textkw):
    """
    A function to annotate a heatmap.

    Parameters
    ----------
    im
        The AxesImage to be labeled.
    ann_format
        The format of the annotations inside the heatmap.  This should be either 'time' or 'speed'.
    textcolors
        A pair of colors.  The first is used for values below a threshold,
        the second for those above.
    threshold
        Value in data units according to which the colors from textcolors are
        applied.  If None (the default) uses the middle of the colormap as
        separation.
    **textkw
        All other arguments are forwarded to each call to `text` used to create
        the text labels.
    """

    data = im.get_array()

    # Normalize the threshold to the images color range.
    if threshold is not None:
        threshold = im.norm(threshold)
    else:
        threshold = im.norm(data.max())/2.

    # Set default alignment to center, but allow it to be
    # overwritten by textkw.
    kw = dict(horizontalalignment="center",
              verticalalignment="center")
    kw.update(textkw)

    if ann_format == 'time':
        # Loop over the data and create a `Text` for each "pixel".
        # Change the text's color depending on the data.
        texts = []
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                kw.update(color=textcolors[int(im.norm(data[i, j]) > threshold)])
                text = im.axes.text(j, i, time.strftime("%H:%M:%S", time.gmtime(float(data[i, j]))), **kw)
                texts.append(text)

        return texts
    elif ann_format == 'speed':
        # Loop over the data and create a `Text` for each "pixel".
        # Change the text's color depending on the data.
        texts = []
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                kw.update(color=textcolors[int(im.norm(data[i, j]) > threshold)])
                text = im.axes.text(j, i, '{:6.3f}it/s'.format(data[i, j]), **kw)
                texts.append(text)

        return texts
    else:
        raise ValueError('Unknown format type.')


@baker.command
def gen3_eval(ds_path,  # path of the directory where to find the pre-processed dataset (containing .dat files)
              net_type='JointEmbedding',  # network to use between 'JointEmbedding' and 'DetectionBase'
              batch_size=8192,  # how many samples per batch to load
              min_chunk_size_exponent=4,
              max_chunk_size_exponent=14,
              min_chunks_exponent=3,
              max_chunks_exponent=13,
              epochs=1,
              training_n_samples=0,  # number of training samples to consider
              use_malicious_labels=1,  # whether or not to use malware/benignware labels as a target
              use_count_labels=1,  # whether or not to use the counts as an additional target
              use_tag_labels=1,  # whether or not to use the tags as additional targets
              feature_dimension=2381,  # The input dimension of the model
              # if provided, seed random number generation with this value (defaults None, no seeding)
              random_seed=None,
              # How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
              workers=0):
    """ Train a feed-forward neural network on EMBER 2.0 features, optionally with additional targets as described in
    the ALOHA paper (https://arxiv.org/abs/1903.05700). SMART tags based on (https://arxiv.org/abs/1905.06262).

    Args:
        ds_path: Path of the directory where to find the pre-processed dataset (containing .dat files).
        net_type: Network to use between 'JointEmbedding' and 'DetectionBase'. (default: 'JointEmbedding')
        min_chunk_size_exponent:
        max_chunk_size_exponent:
        min_chunks_exponent:
        max_chunks_exponent:
        batch_size: How many samples per batch to load. (default: 8192)
        epochs: How many epochs to train for. (default: 1)
        training_n_samples: Number of training samples to consider (used to access the right files).
                            (default: 0 -> all)
        use_malicious_labels: Whether or (1/0) not to use malware/benignware labels as a target. (default: 1)
        use_count_labels: Whether or not (1/0) to use the counts as an additional target. (default: 1)
        use_tag_labels: Whether or not (1/0) to use the tags as additional targets. (default: 1)
        feature_dimension: The input dimension of the model. (default: 2381 -> EMBER 2.0 feature size)
        random_seed: If provided, seed random number generation with this value. (default: None -> no seeding)
        workers: How many worker processes should the dataloader use (default: None -> use multiprocessing.cpu_count())
    """

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net, compute_loss, device = import_modules(net_type=net_type)

    # start mlflow run
    with mlflow.start_run() as mlrun:

        if net_type == 'JointEmbedding':
            use_tag_labels = 1

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('Running generator alternative 3 cross evaluation..')

        chunk_sizes_iterator = [2 ** x for x in range(min_chunk_size_exponent, max_chunk_size_exponent + 1)]
        chunks_iterator = [2 ** x for x in range(min_chunks_exponent, max_chunks_exponent + 1)]

        elapsed_times = np.zeros(shape=(len(chunk_sizes_iterator), len(chunks_iterator)), dtype=np.float32)
        speeds = np.zeros(shape=(len(chunk_sizes_iterator), len(chunks_iterator)), dtype=np.float32)

        for cs, chunk_size in enumerate(chunk_sizes_iterator):
            for c, chunks in enumerate(chunks_iterator):

                if chunk_size * chunks < batch_size or chunk_size * chunks > MAX_LIMIT:
                    continue

                # create malware-NN model
                model = Net(use_malware=bool(use_malicious_labels),
                            use_counts=bool(use_count_labels),
                            use_tags=bool(use_tag_labels),
                            n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                            feature_dimension=feature_dimension)

                # use Adam optimizer on all the model parameters
                opt = torch.optim.Adam(model.parameters())

                # create generator (a.k.a. Dataloader)
                generator = get_generator(ds_root=ds_path,
                                          batch_size=batch_size,
                                          chunk_size=chunk_size,
                                          chunks=chunks,
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

                current_elapsed_times = [0.0 for _ in range(epochs)]
                current_speeds = [0.0 for _ in range(epochs)]

                for epoch in range(epochs):

                    # set start time
                    start_time = time.time()

                    elapsed_time = 0

                    # for all the training batches
                    for i, (features, labels) in enumerate(generator):
                        opt.zero_grad()  # clear old gradients from the last step

                        # copy current features and allocate them on the selected device (CPU or GPU)
                        features = deepcopy(features).to(device)

                        # perform a forward pass through the network
                        out = model(features)

                        # compute loss given the predicted output from the model
                        loss_dict = compute_loss(out, deepcopy(labels))  # copy the ground truth labels

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

                        elapsed_time = time.time() - start_time

                        # create loss string with the current losses
                        loss_str = " ".join([f"{key} loss:{value:7.3f}" for key, value in loss_dict.items()])
                        loss_str += " | "
                        loss_str += " ".join(
                            [f"{key} mean:{np.mean(value):7.3f}" for key, value in loss_histories.items()])

                        # write on standard out the loss string + other information
                        sys.stdout.write('\r Epoch: {}/{} {}/{} '.format(epoch+1, epochs, i + 1, steps_per_epoch)
                                         + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                         .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),
                                                 time.strftime("%H:%M:%S",
                                                               time.gmtime(steps_per_epoch * elapsed_time / (i + 1))),
                                                 (i + 1) / elapsed_time,
                                                 psutil.virtual_memory().percent)
                                         + loss_str)

                        # flush standard output
                        sys.stdout.flush()
                        del features, labels  # to avoid weird references that lead to generator errors

                    print()

                    current_elapsed_times[epoch] = elapsed_time
                    current_speeds[epoch] = steps_per_epoch / elapsed_time

                elapsed_times[cs][c] = sum(current_elapsed_times)/len(current_elapsed_times)
                speeds[cs][c] = sum(current_speeds)/len(current_speeds)

        time_fig, time_ax = plt.subplots(figsize=(10, 9))
        speed_fig, speed_ax = plt.subplots(figsize=(10, 9))

        time_im, time_cbar = heatmap(elapsed_times, chunk_sizes_iterator, chunks_iterator, ax=time_ax,
                                     cmap="BuGn", cbarlabel="elapsed time [s]")

        speed_im, speed_cbar = heatmap(speeds, chunk_sizes_iterator, chunks_iterator, ax=speed_ax,
                                       cmap="BuGn", cbarlabel="speed [it/s]")

        time_texts = annotate_heatmap(time_im, ann_format='time', fontsize='x-small')
        speed_texts = annotate_heatmap(speed_im, ann_format='speed', fontsize='x-small')

        time_fig.tight_layout()
        speed_fig.tight_layout()

        with tempfile.TemporaryDirectory() as tmpdir:
            time_filename = os.path.join(tmpdir, 'times.png')
            speed_filename = os.path.join(tmpdir, 'speeds.png')
            time_fig.savefig(time_filename)
            speed_fig.savefig(speed_filename)

            # log files
            mlflow.log_artifact(time_filename)
            mlflow.log_artifact(speed_filename)

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()