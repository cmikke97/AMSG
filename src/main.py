import os
import baker

import mlflow
from mlflow.utils import mlflow_tags
from mlflow.entities import RunStatus

from logzero import logger

from mlflow.tracking.fluent import _get_experiment_id


def _already_ran(entry_point_name,  # entry point name of the run
                 parameters,  # parameters of the run
                 git_commit,  # git version of the code run
                 experiment_id=None):  # experiment id

    """Best-effort detection of if a run with the given entrypoint name,
    parameters, and experiment id already ran. The run must have completed
    successfully and have at least the parameters provided.
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

        # otherwise (if the run was found and it is exactly the same), return the found run
        return client.get_run(run_info.run_id)

    # if the searched run was not found return 'None'
    logger.warning("No matching run has been found.")
    return None


def _get_or_run(entrypoint,  # entrypoint of the run
                parameters,  # parameters of the run
                git_commit,  # git version of the run
                use_cache=True):  # whether to cache previous runs or not

    # get already executed run, if it exists
    existing_run = _already_ran(entrypoint, parameters, git_commit)
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

    # Note: The entrypoint names are defined in MLproject. The artifact directories
    # are documented by each step's .py file.
    with mlflow.start_run() as active_run:
        # get code git commit version
        git_commit = active_run.data.tags.get(mlflow_tags.MLFLOW_GIT_COMMIT)

        # set dataset destination dir
        dataset_dir = os.path.join(base_dir, "dataset")
        # create dataset destination dir if it does not exist yet
        os.makedirs(dataset_dir, exist_ok=True)
        # run (or get previously executed run) dataset downloader
        download_dataset_run = _get_or_run("download_dataset", {'destination_dir': dataset_dir}, git_commit)

        logger.info(download_dataset_run.info.artifact_uri)
        dataset_base_path_uri = os.path.join(download_dataset_run.info.artifact_uri, "dataset_base_path.txt")
        with open(dataset_base_path_uri, 'r') as f:
            dataset_base_path = f.readline()

        logger.info(dataset_base_path)

        # etl_data_run = _get_or_run(
        #     "etl_data", {"ratings_csv": ratings_csv_uri, "max_row_limit": max_row_limit}, git_commit
        # )
        # ratings_parquet_uri = os.path.join(etl_data_run.info.artifact_uri, "ratings-parquet-dir")
        #
        # # We specify a spark-defaults.conf to override the default driver memory. ALS requires
        # # significant memory. The driver memory property cannot be set by the application itself.
        # als_run = _get_or_run(
        #     "als", {"ratings_data": ratings_parquet_uri, "max_iter": str(als_max_iter)}, git_commit
        # )
        # als_model_uri = os.path.join(als_run.info.artifact_uri, "als-model")
        #
        # keras_params = {
        #     "ratings_data": ratings_parquet_uri,
        #     "als_model_uri": als_model_uri,
        #     "hidden_units": keras_hidden_units,
        # }
        # _get_or_run("train_keras", keras_params, git_commit, use_cache=False)


if __name__ == "__main__":
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
