import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import matplotlib  # comprehensive library for creating static, animated, and interactive visualizations in Python
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
from logzero import logger  # robust and effective logging for Python
from matplotlib import pyplot as plt  # state-based interface to matplotlib, provides a MATLAB-like way of plotting
from sklearn.metrics import accuracy_score  # used to compute the Accuracy classification score
from sklearn.metrics import f1_score  # used to compute the f1 score
from sklearn.metrics import jaccard_score  # used to compute the Jaccard similarity coefficient score
from sklearn.metrics import precision_score  # used to compute the Precision score
from sklearn.metrics import recall_score  # used to compute the Recall score
from sklearn.metrics import roc_auc_score  # used to compute the ROC AUC from prediction scores
from sklearn.metrics import roc_curve  # used to compute the Receiver operating characteristic (ROC) curve

from nets.generators.generators import Dataset

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


SMALL_SIZE = 18
MEDIUM_SIZE = 20
BIGGER_SIZE = 22

plt.rc('font', size=MEDIUM_SIZE)  # controls default text sizes
plt.rc('axes', titlesize=MEDIUM_SIZE)  # fontsize of the axes title
plt.rc('axes', labelsize=MEDIUM_SIZE)  # fontsize of the x and y labels
plt.rc('xtick', labelsize=MEDIUM_SIZE)  # fontsize of the tick labels
plt.rc('ytick', labelsize=MEDIUM_SIZE)  # fontsize of the tick labels
plt.rc('legend', fontsize=MEDIUM_SIZE)  # legend fontsize
plt.rc('figure', titlesize=BIGGER_SIZE)  # fontsize of the figure title


def collect_dataframes(run_id_to_filename_dictionary):  # run ID - filename dictionary
    """ Load dataframes given a run ID - filename dict.

    Args:
        run_id_to_filename_dictionary: Run ID - filename dictionary
    Returns:
        Loaded dataframes in a dictionary of Run ID - dataframe.
    """

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
    """ Get binary predictions for a dataframe/key combination at specific False Positive Rates of interest.

    Args:
        dataframe: A pandas dataframe
        key: The name of the result to get the curve for; if (e.g.) the key 'malware' is provided
             the dataframe is expected to have a column names `pred_malware` and `label_malware`
        target_fprs: The FPRs at which you wish to estimate the TPRs; (1-d numpy array)
    Returns:
        Labels, binary predictions (per fpr).
    """

    # get ROC curve given the dataframe
    fpr, tpr, thresholds = get_roc_curve(dataframe, key)

    # interpolate threshold with respect to the target false positive rates (fprs)
    fpr_thresh = np.interp(target_fprs, fpr, thresholds)

    # extract labels from result dataframe
    labels = np.asarray(dataframe['label_{}'.format(key)])

    # extract predictions from result dataframe
    return labels, {fpr: np.asarray(dataframe['pred_{}'.format(key)] >= fpr_thresh[i], dtype=np.int32)
                    for i, fpr in enumerate(target_fprs)}


def get_tprs_at_fpr(result_dataframe,  # result dataframe for a certain run
                    key,  # the name of the result to get the curve for
                    target_fprs=None):  # The FPRs at which you wish to estimate the TPRs
    """ Estimate the True Positive Rate for a dataframe/key combination at specific False Positive Rates of interest.

    Args:
        result_dataframe: A pandas dataframe
        key: The name of the result to get the curve for; if (e.g.) the key 'malware' is provided
             the dataframe is expected to have a column names `pred_malware` and `label_malware`
        target_fprs: The FPRs at which you wish to estimate the TPRs; None
                     (uses default np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1]) or a 1-d numpy array
    Returns:
        Target_fprs, the corresponding TPRs.
    """

    # if target_fprs is not defined (it is None)
    if target_fprs is None:
        # set some defaults (numpy array)
        target_fprs = np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1])

    # get ROC curve given the dataframe
    fpr, tpr, thresholds = get_roc_curve(result_dataframe, key)

    # return target_fprs and the interpolated values of the ROC curve (tpr/fpr) at points target_fprs
    return np.interp(target_fprs, fpr, tpr)


def get_score_per_fpr(score_function,  # score function to use
                      result_dataframe,  # result dataframe for a certain run
                      key,  # the name of the result to get the curve for
                      target_fprs=None,  # The FPRs at which you wish to estimate the TPRs
                      zero_division=1.0):  # Sets the value to return when there is a zero division
    """ Estimate the Score for a dataframe/key combination using a provided score function at specific False Positive
    Rates of interest.

    Args:
        score_function: Score function to use
        result_dataframe: A pandas dataframe
        key: The name of the result to get the curve for; if (e.g.) the key 'malware' is provided
             the dataframe is expected to have as column names `pred_malware` and `label_malware`
        target_fprs: The FPRs at which you wish to estimate the TPRs; None
                     (uses default np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1]) or a 1-d numpy array
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    Returns:
        Target_fprs, the corresponding Jaccard similarities.
    """

    # if target_fprs is not defined (it is None)
    if target_fprs is None:
        # set some defaults (numpy array)
        target_fprs = np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1])

    # get labels and binary predictions from the result dataframe for the specified key
    labels, bin_predicts = get_binary_predictions(result_dataframe,
                                                  key,
                                                  target_fprs)

    # if the score function is not 'accuracy_score'
    if score_function != accuracy_score:
        # compute score for each fpr
        score = np.asarray([score_function(labels,
                                           bin_predicts[fpr],
                                           zero_division=zero_division)
                            for fpr in target_fprs])
    else:
        # compute score for each fpr (with 'accuracy_score' parameters)
        score = np.asarray([score_function(labels, bin_predicts[fpr]) for fpr in target_fprs])

    # return target_fprs and the interpolated values of the ROC curve (tpr/fpr) at points target_fprs
    return score


def get_all_predictions(result_dataframe,  # result dataframe for a certain run
                        tags,  # tags (list) to extract results for
                        target_fprs=None):  # The FPRs at which you wish to estimate the TPRs
    """ Get labels and binarized predictions (for all keys) for a dataframe at specific False Positive Rates of
    interest.

    Args:
        result_dataframe: A pandas dataframe
        tags: Tags (list) to extract results for
        target_fprs: The FPRs at which you wish to estimate the TPRs; None
                     (uses default np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1]) or a 1-d numpy array
    Returns:
        Labels, target_fprs, corresponding predictions.
    """

    # if target_fprs is not defined (it is None)
    if target_fprs is None:
        # set some defaults (numpy array)
        target_fprs = np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1])

    # extract labels from result dataframe
    labels = np.asarray([(result_dataframe['label_{}'.format(key)]) for key in tags]).T

    # compute roc curve for each tag
    roc_curves = {key: get_roc_curve(result_dataframe, key) for key in tags}

    # compute fpr threshold for each tag given its roc curve
    fpr_thresh = {key: np.interp(target_fprs, roc_curves[key][0], roc_curves[key][2]) for key in tags}

    # for each tag compute predictions at each target fpr
    predictions = [np.asarray([result_dataframe['pred_{}'.format(key)] >= fpr_thresh[key][i]
                               for key in tags], dtype=np.int32).T
                   for i, fpr in enumerate(target_fprs)]

    # return computed labels, target fprs and predictions
    return labels, target_fprs, predictions


def get_roc_curve(result_dataframe,  # result dataframe for a certain run
                  key):  # the name of the result to get the curve for
    """ Get the ROC curve for a single result in a dataframe.

    Args:
        result_dataframe: Result dataframe for a certain run
        key: The name of the result to get the curve for; if (e.g.) the key 'malware' is provided the dataframe is
             expected to have as column names `pred_malware` and `label_malware`
    Returns:
        False positive rates, true positive rates, and thresholds (all np.arrays).
    """

    # extract labels from result dataframe
    labels = result_dataframe['label_{}'.format(key)]
    # extract predictions from result dataframe
    predictions = result_dataframe['pred_{}'.format(key)]

    # return the ROC curve calculated given the labels and predictions
    return roc_curve(labels, predictions)


def get_auc_score(result_dataframe,  # result dataframe for a certain run
                  key):  # the name of the result to get the curve for
    """ Get the Area Under the Curve for the indicated key in the dataframe.

    Args:
        result_dataframe: Result dataframe for a certain run
        key: The name of the result to get the curve for; if (e.g.) the key 'malware' is provided the dataframe is
             expected to have as column names `pred_malware` and `label_malware`
    Returns:
        The AUC for the ROC generated for the provided key.
    """

    # extract labels from result dataframe
    labels = result_dataframe['label_{}'.format(key)]
    # extract predictions from result dataframe
    predictions = result_dataframe['pred_{}'.format(key)]

    # return the ROC AUC score given the labels and predictions
    return roc_auc_score(labels, predictions)


def interpolate_rocs(id_to_roc_dictionary,  # a list of results from get_roc_score (run ID - ROC curve dictionary)
                     eval_fpr_points=None):  # the set of FPR values at which to interpolate the results
    """ This function takes several sets of ROC results and interpolates them to a common set of evaluation (FPR)
    values to allow for computing e.g. a mean ROC or pointwise variance of the curve across multiple model fittings.

    Args:
        id_to_roc_dictionary: A list of results from get_roc_score (run ID - ROC curve dictionary)
        eval_fpr_points: The set of FPR values at which to interpolate the results; defaults to
                         `np.logspace(-6, 0, 1000)`
    Returns:
        eval_fpr_points - the set of common points to which TPRs have been interpolated -- interpolated_tprs - an array
            with one row for each ROC provided, giving the interpolated TPR for that ROC at the corresponding column
            in eval_fpr_points.
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
                             filename,  # the filename to save the resulting figure to
                             include_range=False,  # plot the min/max value as well
                             style=None,  # style (color, linestyle) to use in the plot
                             std_alpha=.2,  # the alpha value for the shading for standard deviation range
                             range_alpha=.1):  # the alpha value for the shading for range, if plotted
    """ Compute the mean and standard deviation of the ROC curve from a sequence of results and plot it with shading.

    Args:
        id_to_dataframe_dictionary: Run ID - result dataframe dictionary
        key: The name of the result to get the curve for
        filename: The filename to save the resulting figure to
        include_range: Plot the min/max value as well
        style: Style (color, linestyle) to use in the plot
        std_alpha: The alpha value for the shading for standard deviation range
        range_alpha: The alpha value for the shading for range, if plotted
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
    # calculate the max value for the ROC AUC score along all runs
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
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def plot_tag_results(dataframe,  # result dataframe
                     filename,  # the name of the file where to save the resulting plot
                     tags):  # tags (list) to extract results for
    """ Produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file.

    Args:
        dataframe: Result dataframe
        filename: The name of the file where to save the resulting plot
        tags: Tags (list) to extract results for
    """

    # calculate ROC curve for each tag of the current (single) run and create a tag - ROC curve dictionary
    all_tag_rocs = {tag: get_roc_curve(dataframe, tag) for tag in tags}

    # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
    eval_fpr_pts, interpolated_rocs = interpolate_rocs(all_tag_rocs)

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # for each tag
    for tag in tags:
        # use a default style
        color, linestyle = style_dict[tag]

        # calculate AUC (area under (ROC) curve) score
        auc = get_auc_score(dataframe, tag)

        # log auc as metric
        mlflow.log_metric("{}_auc".format(tag), auc, step=0)

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
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def plot_tag_mean_results(id_to_dataframe_dictionary,  # run ID - result dataframe dictionary
                          filename,  # the name of the file where to save the resulting plot
                          tags):  # tags (list) to extract results for
    """ Produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file.

    Args:
        id_to_dataframe_dictionary: Run ID - result dataframe dictionary
        filename: The name of the file where to save the resulting plot
        tags: Tags (list) to extract results for
    """

    # if the length of the run ID - result dataframe dictionary is not grater than 1
    if not len(id_to_dataframe_dictionary) > 1:
        # raise an exception
        raise ValueError("Need a minimum of 2 result sets to plot confidence region; found {}".format(
            len(id_to_dataframe_dictionary)
        ))

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # for each tag
    for tag in tags:
        # calculate ROC curve for each run and create a run ID - ROC curve dictionary
        id_to_roc_dictionary = {k: get_roc_curve(df, tag) for k, df in id_to_dataframe_dictionary.items()}

        # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
        fpr_points, interpolated_tprs = interpolate_rocs(id_to_roc_dictionary)

        # stack the interpolated_tprs arrays in sequence vertically -> I obtain a vertical vector of vectors (each of
        # which has all the interpolated values for one single run)
        tpr_array = np.vstack([v for v in interpolated_tprs.values()])

        # calculate mean tpr along dim 0 -> (for each fpr point under examination I calculate the mean along all runs)
        mean_tpr = tpr_array.mean(0)

        # calculate AUC (area under (ROC) curve) score for each run and store them into a numpy array
        aucs = np.array([get_auc_score(v, tag) for v in id_to_dataframe_dictionary.values()])

        # calculate the mean ROC AUC score along all runs
        mean_auc = aucs.mean()

        # use a default style
        color, linestyle = style_dict[tag]

        # log mean auc as metric
        mlflow.log_metric("{}_mean_auc".format(tag), mean_auc, step=0)

        # plot ROC curve
        plt.semilogx(  # make a plot with log scaling on the x axis
            fpr_points,  # false positive rate points as 'x' values
            mean_tpr,  # interpolated mean true positive rates for the current tag as 'y' values
            color + linestyle,  # format string, e.g. 'ro' for red circles
            linewidth=2.0,  # line width in points
            label=f"{tag} (AUC mean):{mean_auc:5.3f}")  # label that will be displayed in the legend

    # place legend in the location, among the nine possible locations, with the minimum overlap with other drawn objects
    plt.legend(loc='best')
    plt.xlim(1e-6, 1.0)  # set the x plot limits
    plt.ylim([0., 1.])  # set the y plot limits
    plt.xlabel('False Positive Rate (FPR)')  # set the label for the x-axis
    plt.ylabel('True Positive Rate (TPR)')  # set the label for the y-axis
    plt.title("per tag mean ROC curve")  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


@baker.command
def compute_scores(results_file,  # complete path to results.csv which contains the output of a model run
                   tag='malware',  # the tag from the results to consider
                   zero_division=1.0):  # sets the value to return when there is a zero division
    """ Estimate some Score values (tpr at fpr, accuracy, recall, precision, f1 score) for a dataframe/key combination
    at specific False Positive Rates of interest.

    Args:
        results_file: Complete path to a results.csv file that contains the output of
                      a model run.
        tag: The tag from the results to consider; defaults to "malware"
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # set target fprs
    target_fprs = np.array([1e-5, 1e-4, 1e-3, 1e-2, 1e-1])

    # compute scores at predefined fprs
    scores_df = pd.DataFrame({'fpr': target_fprs,
                              'tpr at fpr': get_tprs_at_fpr(id_to_dataframe_dict['run'],
                                                            tag,
                                                            target_fprs),
                              'accuracy': get_score_per_fpr(accuracy_score,
                                                            id_to_dataframe_dict['run'],
                                                            tag,
                                                            target_fprs),
                              'recall': get_score_per_fpr(recall_score,
                                                          id_to_dataframe_dict['run'],
                                                          tag,
                                                          target_fprs,
                                                          zero_division),
                              'precision': get_score_per_fpr(precision_score,
                                                             id_to_dataframe_dict['run'],
                                                             tag,
                                                             target_fprs,
                                                             zero_division),
                              'f1': get_score_per_fpr(f1_score,
                                                      id_to_dataframe_dict['run'],
                                                      tag,
                                                      target_fprs,
                                                      zero_division)},
                             index=list(range(1, len(target_fprs) + 1)))

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, tag + "_scores.csv")

        # open loss history file at the specified location
        with open(output_filename, "w") as output_file:
            # serialize scores_df dataframe as a csv file and save it
            scores_df.to_csv(output_file)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "model_scores")


@baker.command
def compute_all_scores(results_file,  # path to results.csv containing the output of a model run
                       use_malicious_labels=1,  # whether or not (1/0) to compute malware/benignware label scores
                       use_tag_labels=1,  # whether or not (1/0) to compute the tag label scores
                       zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute all scores for all tags.

    Args:
        results_file: Path to results.csv containing the output of a model run
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
        zero_division: Sets the value to return when there is a zero division
    """

    # start mlflow run
    with mlflow.start_run():
        # check use_malicious_labels and use_tag_labels, at least one of them should be 1,
        # otherwise the scores cannot be computed -> return
        if not bool(use_malicious_labels) and not bool(use_tag_labels):
            logger.warning('Both "use_malicious_labels" and "use_tag_labels" are set to 0 (false). Returning..')
            return

        # initialize all_tags as an empty list
        all_tags = []
        if bool(use_tag_labels):  # if use_tag_labels is 1, append the tags to all_tags list
            all_tags.extend([tag + "_tag" for tag in Dataset.tags])
        if bool(use_malicious_labels):  # if use_malicious_labels is 1, append malware label to all_tags list
            all_tags.append("malware")

        # for each tag in all_tags list, compute scores
        for tag in all_tags:
            compute_scores(results_file=results_file,
                           tag=tag,
                           zero_division=zero_division)


@baker.command
def compute_mean_scores(results_file,  # path to results.csv containing the output of a model run
                        use_malicious_labels=1,  # whether or not to compute malware/benignware label scores
                        use_tag_labels=1,  # whether or not to compute the tag label scores
                        zero_division=1):  # sets the value to return when there is a zero division
    """ Estimate some mean, per-sample, scores (jaccard similarity and mean per-sample accuracy) for a dataframe at
    specific False Positive Rates of interest.

    Args:
        results_file: Path to results.csv containing the output of a model run
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # start mlflow run
    with mlflow.start_run():
        # if use_tag_labels is set to 0, the mean scores cannot be computed -> return
        if not bool(use_tag_labels):
            logger.warning('"use_tag_labels" is set to 0 (false).'
                           'Jaccard score is not available outside of multi-label classification. Returning..')
            return

        # initialize all_tags as a list containing all tags
        all_tags = [tag + "_tag" for tag in Dataset.tags]

        # create run ID - filename correspondence dictionary (containing just one result file)
        id_to_resultfile_dict = {'run': results_file}

        # read csv result file and obtain a run ID - result dataframe dictionary
        id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

        # get labels, target fprs and predictions from current run results dataframe
        labels, target_fprs, predictions = get_all_predictions(id_to_dataframe_dict['run'], tags=all_tags)

        # compute jaccard scores at each target fpr
        jaccard_scores = np.asarray([jaccard_score(labels,
                                                   predictions[i],
                                                   average='samples',
                                                   zero_division=zero_division)
                                     for i, fpr in enumerate(target_fprs)])

        # compute accuracy scores at each target fpr
        accuracy_scores = np.asarray([accuracy_score(labels,
                                                     predictions[i])
                                      for i, fpr in enumerate(target_fprs)])

        # create scores dataframe
        scores_df = pd.DataFrame({'fpr': target_fprs,
                                  'mean jaccard similarity': jaccard_scores,
                                  'mean per-sample accuracy': accuracy_scores},
                                 index=list(range(1, len(target_fprs) + 1)))

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            output_filename = os.path.join(tempdir, "mean_per_sample_scores.csv")

            # open output file at the specified location
            with open(output_filename, "w") as output_file:
                # serialize scores_df dictionary as a json object and save it to file
                scores_df.to_csv(output_file)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "model_mean_scores")


@baker.command
def plot_tag_result(results_file,  # path to results.csv containing the output of a model run
                    use_malicious_labels=1,  # whether or not (1/0) to compute malware/benignware label scores
                    use_tag_labels=1):  # whether or not (1/0) to compute the tag label scores
    """ Takes a result file from a feedforward neural network model that includes all tags, and produces multiple
    overlaid ROC plots for each tag individually.

    Args:
        results_file: Path to results.csv containing the output of a model run
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
    """

    # start mlflow run
    with mlflow.start_run():
        # check use_malicious_labels and use_tag_labels, at least one of them should be 1, otherwise the tag
        # results cannot be calulated -> return
        if not bool(use_malicious_labels) and not bool(use_tag_labels):
            logger.warning('Both "use_malicious_labels" and "use_tag_labels" are set to 0 (false). Returning..')
            return

        # initialize all_tags as an empty list
        all_tags = []
        if bool(use_tag_labels):  # if use_tag_labels is 1, append the tags to all_tags list
            all_tags.extend([tag + "_tag" for tag in Dataset.tags])
        if bool(use_malicious_labels):  # if use_malicious_labels is 1, append malware label to all_tags list
            all_tags.append("malware")

        # create run ID - filename correspondence dictionary (containing just one result file)
        id_to_resultfile_dict = {'run': results_file}

        # read csv result file and obtain a run ID - result dataframe dictionary
        id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            output_filename = os.path.join(tempdir, "results.png")

            # produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file
            plot_tag_results(id_to_dataframe_dict['run'], output_filename, tags=all_tags)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "model_results")


def plot_tag_mean_result(run_to_filename_json,  # A json file that contains a key-value map that links run
                         # IDs to the full path to a results file (including the file name)
                         all_tags):  # list of all tags to plot results of
    """ Computes the mean of the TPR at a range of FPRS (the ROC curve) over several sets of results (at least 2 runs)
        for all tags (provided) and produces multiple overlaid ROC plots for each tag individually.
        The run_to_filename_json file must have the following format:
        {"run_id_0": "/full/path/to/results.csv/for/run/0/results.csv",
         "run_id_1": "/full/path/to/results.csv/for/run/1/results.csv",
          ...
        }

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        all_tags: list of all tags to plot results of
    """

    # open json containing run ID - filename correspondences and decode it as json object
    id_to_resultfile_dict = json.load(open(run_to_filename_json, 'r'))

    # read csv result files and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, "all_mean_results.png")

        # produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file
        plot_tag_mean_results(id_to_dataframe_dict, output_filename, tags=all_tags)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "model_results")


@baker.command
def plot_roc_distribution_for_tag(run_to_filename_json,  # A json file that contains a key-value map that links run
                                  # IDs to the full path to a results file (including the file name)
                                  tag_to_plot='malware',  # the tag from the results to plot
                                  linestyle=None,  # the linestyle to use in the plot (if None use some defaults)
                                  color=None,  # the color to use in the plot (if None use some defaults)
                                  include_range=False,  # plot the min/max value as well
                                  std_alpha=.2,  # the alpha value for the shading for standard deviation range
                                  range_alpha=.1):  # the alpha value for the shading for range, if plotted
    """ Compute the mean and standard deviation of the TPR at a range of FPRS (the ROC curve) over several sets of
    results (at least 2 runs) for a given tag. The run_to_filename_json file must have the following format:
    {"run_id_0": "/full/path/to/results.csv/for/run/0/results.csv",
     "run_id_1": "/full/path/to/results.csv/for/run/1/results.csv",
      ...
    }

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        tag_to_plot: The tag from the results to plot; defaults to "malware"
        linestyle: The linestyle to use in the plot (defaults to the tag value in plot.style_dict)
        color: The color to use in the plot (defaults to the tag value in plot.style_dict)
        include_range: Plot the min/max value as well (default False)
        std_alpha: The alpha value for the shading for standard deviation range (default 0.2)
        range_alpha: The alpha value for the shading for range, if plotted (default 0.1)
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

    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, tag_to_plot + "_results.png")

        # plot roc curve with confidence
        plot_roc_with_confidence(id_to_dataframe_dict,
                                 tag_to_plot,
                                 output_filename,
                                 include_range=include_range,
                                 style=style,
                                 std_alpha=std_alpha,
                                 range_alpha=range_alpha)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "model_results")


@baker.command
def plot_all_roc_distributions(run_to_filename_json,  # run - filename json file path
                               use_malicious_labels=1,  # whether or not (1/0) to compute malware label scores
                               use_tag_labels=1):  # whether or not (1/0) to compute the tag label scores
    """ Plot ROC distributions for all tags.

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
    """

    # start mlflow run
    with mlflow.start_run():
        # check use_malicious_labels and use_tag_labels, at least one of them should be 1, otherwise the roc
        # distributions cannot be calculated -> return
        if not bool(use_malicious_labels) and not bool(use_tag_labels):
            logger.warning('Both "use_malicious_labels" and "use_tag_labels" are set to 0 (false). Returning..')
            return

        # initialize all_tags as an empty list
        all_tags = []
        if bool(use_tag_labels):  # if use_tag_labels is 1, append the tags to all_tags list
            all_tags.extend([tag + "_tag" for tag in Dataset.tags])
        if bool(use_malicious_labels):  # if use_malicious_labels is 1, append malware label to all_tags list
            all_tags.append("malware")

        plot_tag_mean_result(run_to_filename_json=run_to_filename_json,
                             all_tags=all_tags)

        # for each tag in all_tags, compute and plot roc distribution
        for tag in all_tags:
            plot_roc_distribution_for_tag(run_to_filename_json=run_to_filename_json,
                                          tag_to_plot=tag)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
