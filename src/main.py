import configparser
import os
import tempfile

import baker

import mlflow
from mlflow.utils import mlflow_tags
from mlflow.entities import RunStatus

from logzero import logger
from urllib import parse

import json

from mlflow.tracking.fluent import _get_experiment_id


def _already_ran(entry_point_name,  # entry point name of the run
                 parameters,  # parameters of the run
                 git_commit,  # git version of the code run
                 experiment_id=None,  # experiment id
                 resume=False):  # whether to resume a failed/killed previous run or not

    """Best-effort detection of if a run with the given entrypoint name,
    parameters, and experiment id already ran. The run must have completed
    successfully and have at least the parameters provided.

    :param entry_point_name: Entry point name of the run
    :param parameters: Parameters of the run
    :param git_commit: Git version of the code run
    :param experiment_id: Experiment id (default: None)
    :param resume: Whether to resume a failed/killed previous run or not (default: False)
    """
    # if experiment ID is not provided retrieve current experiment ID
    experiment_id = experiment_id if experiment_id is not None else _get_experiment_id()
    # instantiate MLflowClient (creates and manages experiments and runs)
    client = mlflow.tracking.MlflowClient()
    # get reversed list of run information (from last to first)
    all_run_infos = reversed(client.list_run_infos(experiment_id))
    # for all runs info
    for run_info in all_run_infos:
        # fetch run from backend store
        full_run = client.get_run(run_info.run_id)
        # get run dictionary of tags
        tags = full_run.data.tags
        # if there is no entry point, or the entry point for the run is different from 'entry_point_name', continue
        if tags.get(mlflow_tags.MLFLOW_PROJECT_ENTRY_POINT, None) != entry_point_name:
            continue
        # initialize 'match_failed' bool to false
        match_failed = False
        # for each parameter in the provided run parameters
        for param_key, param_value in parameters.items():
            # get run param value from the run dictionary of parameters
            run_value = full_run.data.params.get(param_key)
            # if the current parameter value is different from the run parameter set 'match_failed' to true and break
            if run_value != param_value:
                match_failed = True
                break
        # if the current run is not the one we are searching for go to the next one
        if match_failed:
            continue

        # if the run is currently running, go to the next one
        if run_info.to_proto().status != RunStatus.FINISHED:
            logger.warning("Run matched, but is not FINISHED, so skipping " "(run_id={}, status={})"
                           .format(run_info.run_id, run_info.status))
            continue

        # get previous run git commit version
        previous_version = tags.get(mlflow_tags.MLFLOW_GIT_COMMIT, None)
        # if the previous version is different from the current one, go to the next one
        if git_commit != previous_version:
            logger.warning("Run matched, but has a different source version, so skipping (found={}, expected={})"
                           .format(previous_version, git_commit))
            continue

        # if resume is enabled and the run was failed or killed, resume it and, when finished, return it
        if resume and (run_info.to_proto().status == RunStatus.FAILED or
                       run_info.to_proto().status == RunStatus.KILLED):
            logger.info("Resuming run with entrypoint=%s and parameters=%s" % (entry_point_name, parameters))
            with mlflow.start_run(run_id=run_info.run_id) as submitted_run:
                return mlflow.tracking.MlflowClient().get_run(submitted_run.to_proto().run_id)

        # otherwise (if the run was found and it is exactly the same), return the found run
        return client.get_run(run_info.run_id)

    # if the searched run was not found return 'None'
    logger.warning("No matching run has been found.")
    return None


def _get_or_run(entrypoint,  # entrypoint of the run
                parameters,  # parameters of the run
                git_commit,  # git version of the run
                use_cache=True,  # whether to cache previous runs or not
                resume=False):  # whether to resume a failed/killed previous run or not

    """
    Get previously executed run, if it exists, or launch run.

    :param entrypoint: Entrypoint of the run
    :param parameters: Parameters of the run
    :param git_commit: Git version of the run
    :param use_cache: Whether to cache previous runs or not
    :param resume: Whether to resume a failed/killed previous run or not
    """

    # get already executed run, if it exists
    existing_run = _already_ran(entrypoint, parameters, git_commit, resume=resume)
    # if we want to cache previous runs and we found a previously executed run, return found run
    if use_cache and existing_run:
        logger.info("Found existing run for entrypoint={} and parameters={}".format(entrypoint, parameters))
        return existing_run
    # otherwise, submit (start) run and return it
    logger.info("Launching new run for entrypoint=%s and parameters=%s" % (entrypoint, parameters))
    submitted_run = mlflow.run(".", entrypoint, parameters=parameters)
    return mlflow.tracking.MlflowClient().get_run(submitted_run.run_id)


@baker.command
def workflow(base_dir):  # base tool path
    """
    Automatic Malware Signature Generation MLflow workflow.

    :param base_dir: base tool path
    """
    # get config file path
    src_dir = os.path.dirname(os.path.abspath(__file__))
    config_filepath = os.path.join(src_dir, 'config.ini')

    # instantiate config parser and read config file
    config = configparser.ConfigParser()
    config.read(config_filepath)

    # get variables from config file
    runs = int(config['jointEmbedding']['runs'])
    batch_size = int(config['jointEmbedding']['batch_size'])
    epochs = int(config['jointEmbedding']['epochs'])
    use_malicious_labels = int(config['jointEmbedding']['use_malicious_labels'])
    use_count_labels = int(config['jointEmbedding']['use_count_labels'])

    training_n_samples = int(config['sorel20mDataset']['training_n_samples'])
    validation_n_samples = int(config['sorel20mDataset']['validation_n_samples'])
    test_n_samples = int(config['sorel20mDataset']['test_n_samples'])

    # Note: The entrypoint names are defined in MLproject. The artifact directories
    # are documented by each step's .py file.
    with mlflow.start_run() as active_run:
        # get code git commit version
        git_commit = active_run.data.tags.get(mlflow_tags.MLFLOW_GIT_COMMIT)

        # set dataset destination dir
        dataset_dir = os.path.join(base_dir, "dataset")
        # run (or get previously executed run) dataset downloader
        download_dataset_run = _get_or_run("download_dataset", {'destination_dir': dataset_dir}, git_commit)

        # get dataset_base_path (path pointing to the folder containing meta.db)
        dataset_base_path_uri = os.path.join(download_dataset_run.info.artifact_uri, "dataset_base_path.txt")
        with open(parse.unquote(parse.urlparse(dataset_base_path_uri).path), 'r') as f:
            dataset_base_path = f.readline()

        dataset_parent_dir = os.path.dirname(dataset_base_path)
        pre_processed_dataset_dir = os.path.join(dataset_parent_dir, 'pre-processed_dataset')

        # pre-process dataset
        preprocess_dataset_run = _get_or_run("preprocess_dataset", {
            'db_path': dataset_base_path,
            'destination_dir': pre_processed_dataset_dir,
            'training_n_samples': training_n_samples,
            'validation_n_samples': validation_n_samples,
            'test_n_samples': test_n_samples,
            'batch_size': batch_size,
            'remove_missing_features': '',
        }, git_commit)

        results_files = {}

        for training_run_id in range(runs):
            logger.info("initiating training run n. {}".format(str(training_run_id)))
            training_run = _get_or_run("train_network", {
                'db_path': pre_processed_dataset_dir,
                'training_run': training_run_id,
                'batch_size': batch_size,
                'epochs': epochs,
                'use_malicious_labels': use_malicious_labels,
                'use_count_labels': use_count_labels
            }, git_commit, resume=True)

            checkpoint_path = parse.unquote(parse.urlparse(os.path.join(training_run.info.artifact_uri,
                                                                        "model_checkpoints")).path)

            checkpoint_file = os.path.join(checkpoint_path, "epoch_{}.pt".format(epochs))

            evaluation_run = _get_or_run("evaluate_network", {
                'db_path': pre_processed_dataset_dir,
                'checkpoint_file': checkpoint_file,
                'batch_size': batch_size,
                'evaluate_malware': use_malicious_labels,
                'evaluate_count': use_count_labels
            }, git_commit, resume=True)

            results_path = parse.unquote(parse.urlparse(os.path.join(evaluation_run.info.artifact_uri,
                                                                     "model_results")).path)

            results_file = os.path.join(results_path, "results.csv")

            # add file path to results_files dictionary (used for plotting results)
            results_files["run_id_" + str(training_run_id)] = os.path.join(results_file)

            per_tag_plot_run = _get_or_run("plot_tag_result", {
                'results_file': results_file
            }, git_commit, resume=True)

            compute_all_scores_run = _get_or_run("compute_all_scores", {
                'results_file': results_file
            }, git_commit, resume=True)

            compute_mean_scores_run = _get_or_run("compute_mean_scores", {
                'results_file': results_file
            }, git_commit, resume=True)

        # create temp dir
        with tempfile.TemporaryDirectory() as tempdir:
            # set run-to-filename file path
            run_to_filename = os.path.join(tempdir, "results.json")

            # create and open the results.json file in write mode
            with open(run_to_filename, "w") as output_file:
                # save results_files dictionary as a json file
                json.dump(results_files, output_file)

            # plot all roc distributions
            per_tag_plot_runs = _get_or_run("plot_all_roc_distributions", {
                'run_to_filename_json': run_to_filename
            }, git_commit, resume=True)

            # log run-to-filename
            mlflow.log_artifact(run_to_filename, "run_to_filename")


if __name__ == "__main__":
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
