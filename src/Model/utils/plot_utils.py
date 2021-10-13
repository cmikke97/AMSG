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

import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
from matplotlib import pyplot as plt  # state-based interface to matplotlib, provides a MATLAB-like way of plotting
from sklearn.metrics import accuracy_score  # used to compute the Accuracy classification score
from sklearn.metrics import f1_score  # used to compute the f1 score
from sklearn.metrics import precision_score  # used to compute the Precision score
from sklearn.metrics import recall_score  # used to compute the Recall score
from sklearn.metrics import roc_auc_score  # used to compute the ROC AUC from prediction scores
from sklearn.metrics import roc_curve  # used to compute the Receiver operating characteristic (ROC) curve


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


def get_all_predictions(result_dataframe,  # result dataframe for a certain run
                        keys,  # keys (list) to extract results for
                        target_fprs=None):  # The FPRs at which you wish to estimate the TPRs
    """ Get labels and binarized predictions (for all keys) for a dataframe at specific False Positive Rates of
    interest.

    Args:
        result_dataframe: A pandas dataframe
        keys: Keys (list) to extract results for
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
    labels = np.asarray([(result_dataframe['label_{}'.format(key)]) for key in keys]).T

    # compute roc curve for each key
    roc_curves = {key: get_roc_curve(result_dataframe, key) for key in keys}

    # compute fpr threshold for each tag given its roc curve
    fpr_thresh = {key: np.interp(target_fprs, roc_curves[key][0], roc_curves[key][2]) for key in keys}

    # for each tag compute predictions at each target fpr
    predictions = [np.asarray([result_dataframe['pred_{}'.format(key)] >= fpr_thresh[key][i]
                               for key in keys], dtype=np.int32).T
                   for i, fpr in enumerate(target_fprs)]

    # return computed labels, target fprs and predictions
    return labels, target_fprs, predictions


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
                       but warnings are also raised (default: 1.0)
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


def compute_scores(results_file,  # complete path to results.csv which contains the output of a model run
                   key,  # the key from the results to consider
                   dest_file,  # the filename to save the resulting figure to
                   zero_division=1.0):  # sets the value to return when there is a zero division
    """ Estimate some Score values (tpr at fpr, accuracy, recall, precision, f1 score) for a dataframe/key combination
    at specific False Positive Rates of interest.

    Args:
        results_file: Complete path to a results.csv file that contains the output of
                      a model run.
        key: The key from the results to consider; defaults to "malware"
        dest_file: The filename to save the resulting scores to
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised (default: 1.0)
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
                                                            key,
                                                            target_fprs),
                              'accuracy': get_score_per_fpr(accuracy_score,
                                                            id_to_dataframe_dict['run'],
                                                            key,
                                                            target_fprs),
                              'recall': get_score_per_fpr(recall_score,
                                                          id_to_dataframe_dict['run'],
                                                          key,
                                                          target_fprs,
                                                          zero_division),
                              'precision': get_score_per_fpr(precision_score,
                                                             id_to_dataframe_dict['run'],
                                                             key,
                                                             target_fprs,
                                                             zero_division),
                              'f1': get_score_per_fpr(f1_score,
                                                      id_to_dataframe_dict['run'],
                                                      key,
                                                      target_fprs,
                                                      zero_division)},
                             index=list(range(1, len(target_fprs) + 1)))

    # open destination file
    with open(dest_file, "w") as output_file:
        # serialize scores_df dataframe as a csv file and save it
        scores_df.to_csv(output_file)


def plot_roc_with_confidence(id_to_dataframe_dictionary,  # run ID - result dataframe dictionary
                             key,  # the name of the result to get the curve for
                             filename,  # the filename to save the resulting figure to
                             style,  # style (color, linestyle) to use in the plot
                             include_range=False,  # plot the min/max value as well
                             std_alpha=.2,  # the alpha value for the shading for standard deviation range
                             range_alpha=.1):  # the alpha value for the shading for range, if plotted
    """ Compute the mean and standard deviation of the ROC curve from a sequence of results and plot it with shading.

    Args:
        id_to_dataframe_dictionary: Run ID - result dataframe dictionary
        key: The name of the result to get the curve for
        filename: The filename to save the resulting figure to
        style: Style (color, linestyle) to use in the plot
        include_range: Plot the min/max value as well (default: False)
        std_alpha: The alpha value for the shading for standard deviation range (default: .2)
        range_alpha: The alpha value for the shading for range, if plotted (default: .1)
    """

    # if the length of the run ID - result dataframe dictionary is not grater than 1
    if not len(id_to_dataframe_dictionary) > 1:
        # raise an exception
        raise ValueError("Need a minimum of 2 result sets to plot confidence region; found {}".format(
            len(id_to_dataframe_dictionary)
        ))

    # if the style was not defined (it is None)
    if style is None:
        raise ValueError(
            "No default style information is available for key {}; please provide (linestyle, color)".format(key))
    else:  # otherwise (the style was defined)
        color, linestyle = style  # get linestyle and color from style

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
    plt.close()
