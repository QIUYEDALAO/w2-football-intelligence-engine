# W2 Prediction Timeline V1

Prediction phases: T_72H, T_48H, T_24H, T_12H, T_6H, T_3H, T_1H, T_30M, T_10M, CLOSING.

Every run records analysis_phase, as_of_time_utc, data_cutoff_utc, odds_snapshot_id, model_run_id, feature_snapshot_id, generated_at_utc. Each phase is an independent prediction. Later snapshots never overwrite earlier snapshots. T_24H cannot use T_1H or closing data. Closing is for closing analysis and postmatch evaluation. File modification time is not business time; future storage must keep event_time, provider_updated_at, ingested_at, and as_of_time.
