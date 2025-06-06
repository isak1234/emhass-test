# -*- coding: utf-8 -*-
"""
This is a script for analysis plot.
To use this script you will need plotly and kaleido. Install them using:
    pip install plotly
    pip install kaleido
Before running this script you should perform a perfect optimization for each type of cost function:
profit, cost and self-consumption
"""

import pathlib

import pandas as pd
import plotly.io as pio

from emhass.forecast import Forecast
from emhass.optimization import Optimization
from emhass.retrieve_hass import RetrieveHass
from emhass.utils import (
    build_config,
    build_params,
    build_secrets,
    get_days_list,
    get_logger,
    get_root,
    get_yaml_parse,
)

pio.renderers.default = "browser"
pd.options.plotting.backend = "plotly"

# the root folder
root = pathlib.Path(str(get_root(__file__, num_parent=2)))
emhass_conf = {}
emhass_conf["data_path"] = root / "data/"
emhass_conf["root_path"] = root / "src/emhass/"
emhass_conf["docs_path"] = root / "docs/"
emhass_conf["config_path"] = root / "config.json"
emhass_conf["secrets_path"] = root / "secrets_emhass.yaml"
emhass_conf["defaults_path"] = emhass_conf["root_path"] / "data/config_defaults.json"
emhass_conf["associations_path"] = emhass_conf["root_path"] / "data/associations.csv"

# create logger
logger, ch = get_logger(__name__, emhass_conf, save_to_file=False)


def get_forecast_optim_objects(
    retrieve_hass_conf, optim_conf, plant_conf, params, get_data_from_file
):
    fcst = Forecast(
        retrieve_hass_conf,
        optim_conf,
        plant_conf,
        params,
        emhass_conf,
        logger,
        get_data_from_file=get_data_from_file,
    )
    df_weather = fcst.get_weather_forecast(method="solar.forecast")
    P_PV_forecast = fcst.get_power_from_weather(df_weather)
    P_load_forecast = fcst.get_load_forecast(method=optim_conf["load_forecast_method"])
    df_input_data_dayahead = pd.concat([P_PV_forecast, P_load_forecast], axis=1)
    df_input_data_dayahead.columns = ["P_PV_forecast", "P_load_forecast"]
    opt = Optimization(
        retrieve_hass_conf,
        optim_conf,
        plant_conf,
        fcst.var_load_cost,
        fcst.var_prod_price,
        "profit",
        emhass_conf,
        logger,
    )
    return fcst, P_PV_forecast, P_load_forecast, df_input_data_dayahead, opt


if __name__ == "__main__":
    get_data_from_file = False
    params = None
    save_figures = False
    # Build params with default config and secrets file
    config = build_config(emhass_conf, logger, emhass_conf["defaults_path"])
    _, secrets = build_secrets(
        emhass_conf, logger, secrets_path=emhass_conf["secrets_path"], no_response=True
    )
    params = build_params(emhass_conf, secrets, config, logger)
    retrieve_hass_conf, optim_conf, plant_conf = get_yaml_parse(params, logger)
    rh = RetrieveHass(
        retrieve_hass_conf["hass_url"],
        retrieve_hass_conf["long_lived_token"],
        retrieve_hass_conf["optimization_time_step"],
        retrieve_hass_conf["time_zone"],
        params,
        emhass_conf,
        logger,
    )
    days_list = get_days_list(retrieve_hass_conf["historic_days_to_retrieve"])
    var_list = [
        retrieve_hass_conf["sensor_power_load_no_var_loads"],
        retrieve_hass_conf["sensor_power_photovoltaics"],
    ]
    rh.get_data(
        days_list, var_list, minimal_response=False, significant_changes_only=False
    )
    rh.prepare_data(
        retrieve_hass_conf["sensor_power_load_no_var_loads"],
        load_negative=retrieve_hass_conf["load_negative"],
        set_zero_min=retrieve_hass_conf["set_zero_min"],
        var_replace_zero=retrieve_hass_conf["sensor_replace_zero"],
        var_interp=retrieve_hass_conf["sensor_linear_interp"],
    )
    df_input_data = rh.df_final.copy()
    fcst, P_PV_forecast, P_load_forecast, df_input_data_dayahead, opt = (
        get_forecast_optim_objects(
            retrieve_hass_conf, optim_conf, plant_conf, params, get_data_from_file
        )
    )
    df_input_data = fcst.get_load_cost_forecast(df_input_data)
    df_input_data = fcst.get_prod_price_forecast(df_input_data)

    template = "presentation"
    y_axis_title = "Power (W)"

    # Let's plot the input data
    fig_inputs1 = df_input_data[
        [
            str(retrieve_hass_conf["sensor_power_photovoltaics"]),
            str(retrieve_hass_conf["sensor_power_load_no_var_loads"] + "_positive"),
        ]
    ].plot()
    fig_inputs1.layout.template = template
    fig_inputs1.update_yaxes(title_text=y_axis_title)
    fig_inputs1.update_xaxes(title_text="Time")
    fig_inputs1.show()
    if save_figures:
        fig_inputs1.write_image(
            emhass_conf["docs_path"] / "images/inputs_power.svg",
            width=1080,
            height=0.8 * 1080,
        )

    fig_inputs2 = df_input_data[["unit_load_cost", "unit_prod_price"]].plot()
    fig_inputs2.layout.template = template
    fig_inputs2.update_yaxes(title_text="Load cost and production sell price (EUR)")
    fig_inputs2.update_xaxes(title_text="Time")
    fig_inputs2.show()
    if save_figures:
        fig_inputs2.write_image(
            emhass_conf["docs_path"] / "images/inputs_cost_price.svg",
            width=1080,
            height=0.8 * 1080,
        )

    fig_inputs_dah = df_input_data_dayahead.plot()
    fig_inputs_dah.layout.template = template
    fig_inputs_dah.update_yaxes(title_text=y_axis_title)
    fig_inputs_dah.update_xaxes(title_text="Time")
    fig_inputs_dah.show()
    if save_figures:
        fig_inputs_dah.write_image(
            emhass_conf["docs_path"] / "images/inputs_dayahead.svg",
            width=1080,
            height=0.8 * 1080,
        )

    # Let's first perform a perfect optimization
    opt_res = opt.perform_perfect_forecast_optim(df_input_data, days_list)
    fig_res = opt_res[["P_deferrable0", "P_deferrable1", "P_grid"]].plot()
    fig_res.layout.template = template
    fig_res.update_yaxes(title_text=y_axis_title)
    fig_res.update_xaxes(title_text="Time")
    fig_res.show()
    if save_figures:
        fig_res.write_image(
            emhass_conf["docs_path"]
            / "images/optim_results_PV_defLoads_perfectOptim.svg",
            width=1080,
            height=0.8 * 1080,
        )

    print(
        "System with: PV, two deferrable loads, perfect optimization, profit >> total cost function sum: "
        + str(opt_res["cost_profit"].sum())
    )

    # And then perform a dayahead optimization
    df_input_data_dayahead = fcst.get_load_cost_forecast(df_input_data_dayahead)
    df_input_data_dayahead = fcst.get_prod_price_forecast(df_input_data_dayahead)
    opt_res_dah = opt.perform_dayahead_forecast_optim(
        df_input_data_dayahead, P_PV_forecast, P_load_forecast
    )
    fig_res_dah = opt_res_dah[["P_deferrable0", "P_deferrable1", "P_grid"]].plot()
    fig_res_dah.layout.template = template
    fig_res_dah.update_yaxes(title_text=y_axis_title)
    fig_res_dah.update_xaxes(title_text="Time")
    fig_res_dah.show()
    if save_figures:
        fig_res_dah.write_image(
            emhass_conf["docs_path"]
            / "images/optim_results_PV_defLoads_dayaheadOptim.svg",
            width=1080,
            height=0.8 * 1080,
        )

    print(
        "System with: PV, two deferrable loads, dayahead optimization, profit >> total cost function sum: "
        + str(opt_res_dah["cost_profit"].sum())
    )

    # Let's simplify to a system with only two deferrable loads, no PV installation
    retrieve_hass_conf["solar_forecast_kwp"] = 0
    fcst, P_PV_forecast, P_load_forecast, df_input_data_dayahead, opt = (
        get_forecast_optim_objects(
            retrieve_hass_conf, optim_conf, plant_conf, params, get_data_from_file
        )
    )
    df_input_data_dayahead = fcst.get_load_cost_forecast(df_input_data_dayahead)
    df_input_data_dayahead = fcst.get_prod_price_forecast(df_input_data_dayahead)
    opt_res_dah = opt.perform_dayahead_forecast_optim(
        df_input_data_dayahead, P_PV_forecast, P_load_forecast
    )
    fig_res_dah = opt_res_dah[["P_deferrable0", "P_deferrable1", "P_grid"]].plot()
    fig_res_dah.layout.template = template
    fig_res_dah.update_yaxes(title_text=y_axis_title)
    fig_res_dah.update_xaxes(title_text="Time")
    fig_res_dah.show()
    if save_figures:
        fig_res_dah.write_image(
            emhass_conf["docs_path"]
            / "images/optim_results_defLoads_dayaheadOptim.svg",
            width=1080,
            height=0.8 * 1080,
        )

    print(
        "System with: two deferrable loads, dayahead optimization, profit >> total cost function sum: "
        + str(opt_res_dah["cost_profit"].sum())
    )

    # Now a complete system with PV, Battery and two deferrable loads
    retrieve_hass_conf["solar_forecast_kwp"] = 5
    optim_conf["set_use_battery"] = True
    fcst, P_PV_forecast, P_load_forecast, df_input_data_dayahead, opt = (
        get_forecast_optim_objects(
            retrieve_hass_conf, optim_conf, plant_conf, params, get_data_from_file
        )
    )
    df_input_data_dayahead = fcst.get_load_cost_forecast(df_input_data_dayahead)
    df_input_data_dayahead = fcst.get_prod_price_forecast(df_input_data_dayahead)
    opt_res_dah = opt.perform_dayahead_forecast_optim(
        df_input_data_dayahead, P_PV_forecast, P_load_forecast
    )
    fig_res_dah = opt_res_dah[
        ["P_deferrable0", "P_deferrable1", "P_grid", "P_batt", "P_v2g"]
    ].plot()
    fig_res_dah.layout.template = template
    fig_res_dah.update_yaxes(title_text=y_axis_title)
    fig_res_dah.update_xaxes(title_text="Time")
    fig_res_dah.show()
    if save_figures:
        fig_res_dah.write_image(
            emhass_conf["docs_path"]
            / "images/optim_results_PV_Batt_defLoads_dayaheadOptim.svg",
            width=1080,
            height=0.8 * 1080,
        )
    fig_res_dah = opt_res_dah[["SOC_opt"]].plot()
    fig_res_dah.layout.template = template
    fig_res_dah.update_yaxes(title_text="Battery State of Charge (%)")
    fig_res_dah.update_xaxes(title_text="Time")
    fig_res_dah.show()
    if save_figures:
        fig_res_dah.write_image(
            emhass_conf["docs_path"]
            / "images/optim_results_PV_Batt_defLoads_dayaheadOptim_SOC.svg",
            width=1080,
            height=0.8 * 1080,
        )

    print(
        "System with: PV, Battery, two deferrable loads, dayahead optimization, profit >> total cost function sum: "
        + str(opt_res_dah["cost_profit"].sum())
    )
