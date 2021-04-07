import json  # JSON encoder and decoder

import baker  # Easy, powerful access to Python functions from the command line
import matplotlib  # Comprehensive library for creating static, animated, and interactive visualizations in Python
import numpy as np  # The fundamental package for scientific computing with Python
# Pandas is a fast, powerful, flexible and easy to use open source data analysis and manipulation tool
import pandas as pd
from matplotlib import pyplot as plt  # State-based interface to matplotlib, provides a MATLAB-like way of plotting
# Used to compute the Area Under the Receiver Operating Characteristic Curve (ROC AUC) from prediction scores
from sklearn.metrics import roc_auc_score
from sklearn.metrics import roc_curve  # Used to compute the Receiver operating characteristic (ROC) curve
from sklearn.metrics import jaccard_score  # Used to compute the Jaccard similarity coefficient score
from sklearn.metrics import accuracy_score  # Used to compute the Accuracy classification score
from sklearn.metrics import recall_score  # Used to compute the Recall score
from sklearn.metrics import precision_score  # Used to compute the Precision score
from sklearn.metrics import f1_score  # Used to compute the f1 score

from logzero import logger

matplotlib.use('Agg')  # Select 'Agg' as the backend used for rendering and GUI integration

# define default tags
default_tags = ['adware_tag', 'flooder_tag', 'ransomware_tag',
                'dropper_tag', 'spyware_tag', 'packed_tag',
                'crypto_miner_tag', 'file_infector_tag', 'installer_tag',
                'worm_tag', 'downloader_tag']

# define default tag colors to be used in the graph
default_tag_colors = ['r', 'r', 'r',
                      'g', 'g', 'b',
                      'b', 'm', 'm',
                      'c', 'c']

# define default tag linestyles to be used in the graph
default_tag_linestyles = [':', '--', '-.',
                          ':', '--', ':',
                          '--', ':', '--',
                          ':', '--']

# combine the previously defined information into a "style" dictionary (e.g. {'adware_tag': ('r', ':'), ..})
style_dict = {tag: (color, linestyle) for tag, color, linestyle in zip(default_tags,
                                                                       default_tag_colors,
                                                                       default_tag_linestyles)}

# append style information for label 'malware'
style_dict['malware'] = ('k', '-')


def collect_dataframes(run_id_to_filename_dictionary):  # run ID - filename dictionary
    # instantiate loaded_dataframes
    loaded_dataframes = {}

    # for each element in the run ID - filename dictionary
    for k, v in run_id_to_filename_dictionary.items():
        # read comma-separated values (csv) file into a DataFrame and save it into loaded dataframes dictionary
        loaded_dataframes[k] = pd.read_csv(v)

    return loaded_dataframes  # return all loaded dataframes


def get_binary_predictions(dataframe,  # result dataframe for a certain run
                           key,  # the name of the result to get the curve for
                           target_fprs):  # The FPRs at which you wish to estimate the TPRs
    """
    Get binary predictions for a dataframe/key combination at specific False Positive Rates of interest.
    :param dataframe: a pandas dataframe
    :param key: the name of the result to get the curve for; if (e.g.) the key 'malware' is provided
        the dataframe is expected to have a column names `pred_malware` and `label_malware`
    :param target_fprs: The FPRs at which you wish to estimate the TPRs; (1-d numpy array)
    :return: labels, binary predictions (per fpr)
    """

    # get ROC curve given the dataframe
    fpr, tpr, thresholds = roc_curve(dataframe, key)

    # interpolate threshold with respect to the target false positive rates (fprs)
    fpr_thresh = np.interp(target_fprs, fpr, thresholds)

    # extract labels from result dataframe
    labels = dataframe['label_{}'.format(key)]

    # extract predictions from result dataframe
    return labels, {fpr: int(dataframe['pred_{}'.format(key)] >= fpr_thresh[i]) for i, fpr in enumerate(target_fprs)}


def get_tprs_at_fpr(result_dataframe,  # result dataframe for a certain run
                    key,  # the name of the result to get the curve for
                    target_fprs=None):  # The FPRs at which you wish to estimate the TPRs
    """
    Estimate the True Positive Rate for a dataframe/key combination
    at specific False Positive Rates of interest.
    :param result_dataframe: a pandas dataframe
    :param key: the name of the result to get the curve for; if (e.g.) the key 'malware' is provided
        the dataframe is expected to have a column names `pred_malware` and `label_malware`
    :param target_fprs: The FPRs at which you wish to estimate the TPRs;
        None (uses default np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1]) or a 1-d numpy array
    :return: target_fprs, the corresponding TPRs
    """

    # if target_fprs is not defined (it is None)
    if target_fprs is None:
        # set some defaults (numpy array)
        target_fprs = np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1])

    # get ROC curve given the dataframe
    fpr, tpr, thresholds = get_roc_curve(result_dataframe, key)

    # return target_fprs and the interpolated values of the ROC curve (tpr/fpr) at points target_fprs
    return target_fprs, np.interp(target_fprs, fpr, tpr)


def get_score_per_fpr(score_function,  # score function to use
                      result_dataframe,  # result dataframe for a certain run
                      key,  # the name of the result to get the curve for
                      target_fprs=None):  # The FPRs at which you wish to estimate the TPRs
    """
    Estimate the Score for a dataframe/key combination using a provided score function
    at specific False Positive Rates of interest.
    :param score_function: score function to use
    :param result_dataframe: a pandas dataframe
    :param key: the name of the result to get the curve for; if (e.g.) the key 'malware' is provided
        the dataframe is expected to have a column names `pred_malware` and `label_malware`
    :param target_fprs: The FPRs at which you wish to estimate the TPRs;
        None (uses default np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1]) or a 1-d numpy array
    :return: target_fprs, the corresponding Jaccard similarities
    """

    # if target_fprs is not defined (it is None)
    if target_fprs is None:
        # set some defaults (numpy array)
        target_fprs = np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1])

    labels, bin_predicts = get_binary_predictions(result_dataframe,
                                                  key,
                                                  target_fprs)

    score = {fpr: score_function(labels, bin_predicts[i]) for i, fpr in enumerate(target_fprs)}

    # return target_fprs and the interpolated values of the ROC curve (tpr/fpr) at points target_fprs
    return target_fprs, score


def get_jaccard_similarity_score(result_dataframe,  # result dataframe for a certain run
                                 target_fprs=None):  # The FPRs at which you wish to estimate the TPRs
    """
    Estimate the Jaccard Similarity Score for a dataframe/key combination
    at specific False Positive Rates of interest.
    :param result_dataframe: a pandas dataframe
    :param target_fprs: The FPRs at which you wish to estimate the TPRs;
        None (uses default np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1]) or a 1-d numpy array
    :return: target_fprs, the corresponding Jaccard similarities
    """

    # if target_fprs is not defined (it is None)
    if target_fprs is None:
        # set some defaults (numpy array)
        target_fprs = np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1])

    temp = {fpr: [] for fpr in target_fprs}

    labels_predictions = [get_binary_predictions(result_dataframe, tag, target_fprs) for tag in default_tags]

    logger.info(labels_predictions)

    # jc = {fpr: jaccard_score(labels, bin_predicts[i], average='samples') for i, fpr in enumerate(target_fprs)}

    # return target_fprs and the interpolated values of the ROC curve (tpr/fpr) at points target_fprs
    # return target_fprs, jc


def get_roc_curve(result_dataframe,  # result dataframe for a certain run
                  key):  # the name of the result to get the curve for
    """
    Get the ROC curve for a single result in a dataframe
    :param result_dataframe: a dataframe
    :param key: the name of the result to get the curve for; if (e.g.) the key 'malware' is provided
    the dataframe is expected to have a column names `pred_malware` and `label_malware`
    :return: false positive rates, true positive rates, and thresholds (all np.arrays)
    """

    # extract labels from result dataframe
    labels = result_dataframe['label_{}'.format(key)]
    # extract predictions from result dataframe
    predictions = result_dataframe['pred_{}'.format(key)]

    # return the ROC curve calculated given the labels and predictions
    return roc_curve(labels, predictions)


def get_auc_score(result_dataframe,  # result dataframe for a certain run
                  key):  # the name of the result to get the curve for
    """
    Get the Area Under the Curve for the indicated key in the dataframe
    :param result_dataframe: a dataframe
    :param key: the name of the result to get the curve for; if (e.g.) the key 'malware' is provided
    the dataframe is expected to have a column names `pred_malware` and `label_malware`
    :return: the AUC for the ROC generated for the provided key
    """

    # extract labels from result dataframe
    labels = result_dataframe['label_{}'.format(key)]
    # extract predictions from result dataframe
    predictions = result_dataframe['pred_{}'.format(key)]

    # return the ROC AUC score given the labels and predictions
    return roc_auc_score(labels, predictions)


def interpolate_rocs(id_to_roc_dictionary,  # a list of results from get_roc_score (run ID - ROC curve dictionary)
                     eval_fpr_points=None):  # the set of FPR values at which to interpolate the results
    """
    This function takes several sets of ROC results and interpolates them to a common set of
    evaluation (FPR) values to allow for computing e.g. a mean ROC or pointwise variance of the curve
    across multiple model fittings.
    :param id_to_roc_dictionary: a list of results from get_roc_score (run ID - ROC curve dictionary)
    :param eval_fpr_points: the set of FPR values at which to interpolate the results; defaults to
    `np.logspace(-6, 0, 1000)`
    :return:
        eval_fpr_points  -- the set of common points to which TPRs have been interpolated
        interpolated_tprs -- an array with one row for each ROC provided, giving the interpolated TPR for that ROC at
    the corresponding column in eval_fpr_points
    """

    # if eval_frp_points was not defined (it is None)
    if eval_fpr_points is None:
        # set some default evaluation false positive rate points (fpr points)
        eval_fpr_points = np.logspace(-6, 0, 1000)

    # instantiate interpolated_tprs dictionary
    interpolated_tprs = {}

    # for all the runs
    for k, (fpr, tpr, thresh) in id_to_roc_dictionary.items():
        # interpolate ROC curve (tpr/fpr) at points eval_fpr_points
        interpolated_tprs[k] = np.interp(eval_fpr_points, fpr, tpr)

    # return the eval_fpr_points and interpolated_tprs
    return eval_fpr_points, interpolated_tprs


def plot_roc_with_confidence(id_to_dataframe_dictionary,  # run ID - result dataframe dictionary
                             key,  # the name of the result to get the curve for
                             filename,  # The filename to save the resulting figure to
                             include_range=False,  # plot the min/max value as well
                             style=None,  # style (color, linestyle) to use in the plot
                             std_alpha=.2,  # the alpha value for the shading for standard deviation range
                             range_alpha=.1):  # the alpha value for the shading for range, if plotted
    """
    Compute the mean and standard deviation of the ROC curve from a sequence of results
    and plot it with shading.
    """

    # if the length of the run ID - result dataframe dictionary is not grater than 1
    if not len(id_to_dataframe_dictionary) > 1:
        # raise an exception
        raise ValueError("Need a minimum of 2 result sets to plot confidence region; found {}".format(
            len(id_to_dataframe_dictionary)
        ))

    # if the style was not defined (it is None)
    if style is None:
        # if the key is present inside style_dict then use a default style
        if key in style_dict:
            color, linestyle = style_dict[key]
        else:  # otherwise raise an exception
            raise ValueError(
                "No default style information is available for key {}; please provide (linestyle, color)".format(key))

    else:  # otherwise (the style was defined)
        linestyle, color = style  # get linestyle and color from style

    # calculate ROC curve for each run and create a run ID - ROC curve dictionary
    id_to_roc_dictionary = {k: get_roc_curve(df, key) for k, df in id_to_dataframe_dictionary.items()}

    # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
    fpr_points, interpolated_tprs = interpolate_rocs(id_to_roc_dictionary)

    # stack the interpolated_tprs arrays in sequence vertically -> I obtain a vertical vector of vectors (each of
    # which has all the interpolated values for one single run)
    tpr_array = np.vstack([v for v in interpolated_tprs.values()])

    # calculate mean tpr along dim 0 -> (for each fpr point under examination I calculate the mean along all runs)
    mean_tpr = tpr_array.mean(0)

    # calculate tpr standard deviation by calculating the tpr variance along dim 0 and then calculating the square root
    # -> (for each fpr point under examination I calculate the standard deviation along all runs)
    std_tpr = np.sqrt(tpr_array.var(0))

    # calculate AUC (area under (ROC) curve) score for each run and store them into a numpy array
    aucs = np.array([get_auc_score(v, key) for v in id_to_dataframe_dictionary.values()])

    # calculate the mean ROC AUC score along all runs
    mean_auc = aucs.mean()
    # calculate the min value for the ROC AUC score along all runs
    min_auc = aucs.min()
    # calculate the max value for the ROC AUC score alonf all runs
    max_auc = aucs.max()
    # calculate the standard deviation for the ROC AUC score along all runs
    # (by calculating the ROC AUC score variance and then taking the square root)
    std_auc = np.sqrt(aucs.var())

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # plot ROC curve
    plt.semilogx(  # make a plot with log scaling on the x axis
        fpr_points,  # false positive rate points as 'x' values
        mean_tpr,  # mean true positive rates as 'y' values
        color + linestyle,  # format string, e.g. 'ro' for red circles
        linewidth=2.0,  # line width in points
        # label that will be displayed in the legend
        label=f"{key} (AUC): {mean_auc:5.3f}$\pm${std_auc:5.3f} [{min_auc:5.3f}-{max_auc:5.3f}]")

    # fill uncertainty area around ROC curve
    plt.fill_between(  # fill the area between two horizontal curves
        fpr_points,  # false positive rate points as 'x' values
        mean_tpr - std_tpr,  # mean - standard deviation of true positive rates as 'y' coordinates of the first curve
        mean_tpr + std_tpr,  # mean + standard deviation of true positive rates as 'y' coordinates of the second curve
        color=color,  # set both the edgecolor and the facecolor
        alpha=std_alpha)  # set the alpha value used for blending

    # if the user wants to plot the min/max value as well
    if include_range:
        # fill area between min and max ROC curve values
        plt.fill_between(  # fill the area between two horizontal curves
            fpr_points,  # false positive rate points as 'x' values
            tpr_array.min(0),  # min true positive rates as 'y' coordinates of the first curve
            tpr_array.max(0),  # max true positive rates as 'y' coordinates of the second curve
            color=color,  # set both the edgecolor and the facecolor
            alpha=range_alpha)  # set the alpha value used for blending

    plt.legend()  # place legend on the axes
    plt.xlim(1e-6, 1.0)  # set the x plot limits
    plt.ylim([0., 1.])  # set the y plot limits
    plt.xlabel('False Positive Rate (FPR)')  # set the label for the x-axis
    plt.ylabel('True Positive Rate (TPR)')  # set the label for the y-axis
    plt.title("model ROC curve")  # set plot title
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def plot_tag_results(dataframe,  # result dataframe
                     filename):  # the name of the file in which to save the resulting plot

    # calculate ROC curve for each tag of the current (single) run and create a tag - ROC curve dictionary
    all_tag_rocs = {tag: get_roc_curve(dataframe, tag) for tag in default_tags}

    # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
    eval_fpr_pts, interpolated_rocs = interpolate_rocs(all_tag_rocs)

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # for each tag
    for tag in default_tags:
        # use a default style
        color, linestyle = style_dict[tag]

        # calculate AUC (area under (ROC) curve) score
        auc = get_auc_score(dataframe, tag)

        # plot ROC curve
        plt.semilogx(  # make a plot with log scaling on the x axis
            eval_fpr_pts,  # false positive rate points as 'x' values
            interpolated_rocs[tag],  # interpolated true positive rates for the current tag as 'y' values
            color + linestyle,  # format string, e.g. 'ro' for red circles
            linewidth=2.0,  # line width in points
            label=f"{tag} (AUC):{auc:5.3f}")  # label that will be displayed in the legend

    # place legend in the location, among the nine possible locations, with the minimum overlap with other drawn objects
    plt.legend(loc='best')
    plt.xlim(1e-6, 1.0)  # set the x plot limits
    plt.ylim([0., 1.])  # set the y plot limits
    plt.xlabel('False Positive Rate (FPR)')  # set the label for the x-axis
    plt.ylabel('True Positive Rate (TPR)')  # set the label for the y-axis
    plt.title("per tag ROC curve")  # set plot title
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


@baker.command
def compute_tprs_at_fpr(results_file,  # complete path to results.csv which contains the output of a model run
                        output_filename,  # the name of the file where to save the results
                        tag='malware'):  # the tag from the results to consider
    """
    Estimate the True Positive Rate for a dataframe/key combination
    at specific False Positive Rates of interest.
    :param results_file: complete path to a results.csv file that contains the output of
        a model run.
    :param output_filename: the name of the file where to save the results
    :param tag: the tag from the results to consider; defaults to "malware"
    """
    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    tprs_at_fpr = get_tprs_at_fpr(id_to_dataframe_dict['run'], tag)

    output_file = open(output_filename, "w")  # open loss history file at the specified location

    # serialize tprs_at_fpr dictionary as a json object and save it to file
    json.dump(tprs_at_fpr, output_file)
    output_file.close()  # close loss history file


@baker.command
def compute_scores(results_file,  # complete path to results.csv which contains the output of a model run
                   output_filename,  # the name of the file where to save the results
                   tag='malware'):  # the tag from the results to consider
    """
    Estimate the some Score values for a dataframe/key combination
    at specific False Positive Rates of interest.
    :param results_file: complete path to a results.csv file that contains the output of
    a model run.
    :param output_filename: the name of the file where to save the results
    :param tag: the tag from the results to consider; defaults to "malware"
    """

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # compute scores at predefined fprs
    scores = {'accuracy': get_score_per_fpr(accuracy_score, id_to_dataframe_dict['run'], tag),
              'recall': get_score_per_fpr(recall_score, id_to_dataframe_dict['run'], tag),
              'precision': get_score_per_fpr(precision_score, id_to_dataframe_dict['run'], tag),
              'f1': get_score_per_fpr(f1_score, id_to_dataframe_dict['run'], tag)}

    output_file = open(output_filename, "w")  # open loss history file at the specified location

    # serialize tprs_at_fpr dictionary as a json object and save it to file
    json.dump(scores, output_file)
    output_file.close()  # close loss history file


@baker.command
def get_jaccard_similarity_score(results_file,  # complete path to results.csv which contains the output of a model run
                                 output_filename,  # the name of the file where to save the results
                                 tag='malware'):  # the tag from the results to consider
    """
    Estimate the Jaccard Similarity Score for a dataframe/key combination
    at specific False Positive Rates of interest.
    :param results_file: complete path to a results.csv file that contains the output of
    a model run.
    :param output_filename: the name of the file where to save the results
    :param tag: the tag from the results to consider; defaults to "malware"
    """

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    jaccard_at_fpr = get_jaccard_similarity_score(id_to_dataframe_dict['run'], tag)

    output_file = open(output_filename, "w")  # open loss history file at the specified location

    # serialize tprs_at_fpr dictionary as a json object and save it to file
    json.dump(jaccard_at_fpr, output_file)
    output_file.close()  # close loss history file


@baker.command
def plot_loss_trend(loss_history_path,  # path to loss_history.json that contains the mean loss history of a model run
                    output_filename):  # the name of the file where to save the resulting plot
    """
    Takes a result file from a feedforward neural network model that includes all
    tags, and produces multiple overlaid ROC plots for each tag individually.
    :param loss_history_path: complete path to a loss_history.json file that contains the mean loss history of
        a model run.
    :param output_filename: the name of the file where to save the resulting plot.
    """

    # open loss history file
    loss_history_file = open(loss_history_path, "r")

    # deserialize loss dictionary from json file to python dictionary
    loss_per_epoch = json.load(loss_history_file)

    # close file
    loss_history_file.close()

    # create a figure and a set of subplots
    fig, ax = plt.subplots()

    # get training and validation loss histories separately
    train_loss_history = loss_per_epoch["train"]
    valid_loss_history = loss_per_epoch["valid"]

    # plot training loss
    ax.plot([int(epoch) for epoch in train_loss_history.keys()],
            [loss['total'] for loss in train_loss_history.values()], label='training')

    # plot validation loss
    ax.plot([int(epoch) for epoch in valid_loss_history.keys()],
            [loss['total'] for loss in valid_loss_history.values()], label='validation')

    # set plot axes
    ax.set(xlabel='epoch',
           ylabel='loss',
           title='loss')

    ax.grid()  # display a grid in the plot
    ax.legend()  # display a legend in the plot

    fig.savefig(output_filename)  # save generated figure (plot) to output file


@baker.command
def plot_tag_result(results_file,  # complete path to a results.csv file that contains the output of a model run
                    output_filename):  # the name of the file where to save the resulting plot
    """
    Takes a result file from a feedforward neural network model that includes all
    tags, and produces multiple overlaid ROC plots for each tag individually.
    :param results_file: complete path to a results.csv file that contains the output of
        a model run.
    :param output_filename: the name of the file where to save the resulting plot.
    """

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file
    plot_tag_results(id_to_dataframe_dict['run'], output_filename)


@baker.command
def plot_roc_distribution_for_tag(run_to_filename_json,  # A json file that contains a key-value map that links run
                                  # IDs to the full path to a results file (including the file name)
                                  output_filename,  # The filename to save the resulting figure to
                                  tag_to_plot='malware',  # the tag from the results to plot
                                  linestyle=None,  # the linestyle to use in the plot (if None use some defaults)
                                  color=None,  # the color to use in the plot (if None use some defaults)
                                  include_range=False,  # plot the min/max value as well
                                  std_alpha=.2,  # the alpha value for the shading for standard deviation range
                                  range_alpha=.1):  # the alpha value for the shading for range, if plotted
    """
    Compute the mean and standard deviation of the TPR at a range of FPRS (the ROC curve)
    over several sets of results (at least 2 runs) for a given tag.  The run_to_filename_json file must have
    the following format:
    {"run_id_0": "/full/path/to/results.csv/for/run/0/results.csv",
     "run_id_1": "/full/path/to/results.csv/for/run/1/results.csv",
      ...
    }

    :param run_to_filename_json: A json file that contains a key-value map that links run IDs to
        the full path to a results file (including the file name)
    :param output_filename: The filename to save the resulting figure to
    :param tag_to_plot: the tag from the results to plot; defaults to "malware"
    :param linestyle: the linestyle to use in the plot (defaults to the tag value in
        plot.style_dict)
    :param color: the color to use in the plot (defaults to the tag value in
        plot.style_dict)
    :param include_range: plot the min/max value as well (default False)
    :param std_alpha: the alpha value for the shading for standard deviation range
        (default 0.2)
    :param range_alpha: the alpha value for the shading for range, if plotted
        (default 0.1)
    """

    # open json containing run ID - filename correspondences and decode it as json object
    id_to_resultfile_dict = json.load(open(run_to_filename_json, 'r'))

    # read csv result files and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    if color is None or linestyle is None:  # if either color or linestyle is None
        if not (color is None and linestyle is None):  # if just one of them is None
            raise ValueError("both color and linestyle should either be specified or None")  # raise an exception

        # otherwise select None as style
        style = None

    else:
        # otherwise (both color and linestyle were specified) define the style as a tuple of color and linestyle
        style = (color, linestyle)

    # plot roc curve with confidence
    plot_roc_with_confidence(id_to_dataframe_dict,
                             tag_to_plot,
                             output_filename,
                             include_range=include_range,
                             style=style,
                             std_alpha=std_alpha,
                             range_alpha=range_alpha)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
