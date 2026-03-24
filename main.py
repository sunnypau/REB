"""REB main file"""
import time

from milap.constants import (
    ANCILLARY_ASSUMPTIONS_FILE,
    EXIT_LIMIT_ASSUMPTIONS_FILE,
    MIDT_FLOW_FOLDER,
    MIDT_LOADFACTOR_FOLDER,
    OAG_TOFROM_FOLDER,
    SEA_CITY_PAIRS,
    TAX_ASSUMPTIONS_FILE,
)
from milap.csvloader import (
    AssumptionsLoader,
    FlowFolderLoader,
    LoadFactorFolderLoader,
    ToFromFolderLoader,
)
from milap.revenue import RebDataContainer, RebCalculator, RebPlotter


def template():
    """General template for development"""
    st = time.time()
    flow = FlowFolderLoader(MIDT_FLOW_FOLDER)
    flow.merge_city_pairs(
        SEA_CITY_PAIRS
    )  # I dont like this because I don't want to automatically add city pairs when importing Flow.

    reb_data = RebDataContainer(
        flow,
        LoadFactorFolderLoader(MIDT_LOADFACTOR_FOLDER),
        ToFromFolderLoader(OAG_TOFROM_FOLDER),
        AssumptionsLoader(TAX_ASSUMPTIONS_FILE),
        AssumptionsLoader(ANCILLARY_ASSUMPTIONS_FILE),
        AssumptionsLoader(EXIT_LIMIT_ASSUMPTIONS_FILE),
    )
    


    class User:
        def __init__(self, airline, start_year, end_year=None):
            self.airline = airline
            self.start_year = start_year
            self.end_year = end_year if end_year is not None else start_year

    class Revenue_Analysis:
        # (I am not happy with the class taking df1, df2 and df2_cols at instantiation. Will revisit.)
        def __init__(self, user, df1, df2=None, df2_cols=None):
            if (df2 is None) != (df2_cols is None):
                raise ValueError(
                    "df2 and df2_cols must both be provided together, or both left as None."
                )
            self.user = user
            self.df1 = df1
            self.df2 = df2
            self.df2_cols = df2_cols
            self.df_merged, self.df_airline, self.df_sliced = self._merge()
            self._create_plots()

        # Step 1: merge and slice dataframes
        def _merge(self):
            if self.df2 is not None and self.df2_cols is not None:
                df_merged = self.df1.merge(
                    self.df2[
                        ["Leg Origin Airport", "Leg Destination Airport"]
                        + self.df2_cols
                    ],
                    on=["Leg Origin Airport", "Leg Destination Airport"],
                    how="left",
                )
            else:
                df_merged = self.df1.copy()
            df_merged["RASK"] = df_merged["R_total"] / (
                df_merged["Seats (Total)"] * df_merged["D_trunk"]
            )
            df_airline = df_merged[
                df_merged["Leg Operating Airline"] == self.user.airline
            ].copy()
            df_sliced = df_airline[
                df_airline["Year"].between(self.user.start_year, self.user.end_year)
            ].copy()
            return (
                df_merged,
                df_airline,
                df_sliced,
            )  # in case the dfs are useful to create other plots/tables

        # Step 2: create plots
        def _create_plots(self):
                
            # 1.1.1 General stats
            no_of_routes = self.df_sliced["Airport Pair"].nunique()
            no_of_destinations = self.df_sliced["Leg Destination Airport"].nunique()
            no_of_pax = self.df_sliced["Passengers"].sum()
            total_revenue = self.df_sliced["R_total"].sum()
            total_seats = self.df_sliced["Seats (Total)"].sum()
            load_factor = (no_of_pax / total_seats)

            print(f"""
                {"="*40}
                {self.user.airline} {self.user.start_year} Performance Summary
                {"="*40}
                Total number of routes:         {no_of_routes}
                Total number of destinations:   {no_of_destinations}
                Total number of passengers:     {no_of_pax:,.0f}
                Total revenue:                  {total_revenue:,.0f}
                Average load factor:            {load_factor:,.2%}
                {"="*40}
                """)

            # 1.1.4 Total revenue (year/ month)
            # (I have only prepared a version sorted by calendar month for now)
            plt.figure(figsize=(12, 6))
            self.plot_total_revenue = self.line_plot_yearmonth_sum(
                x_axis="Year-Month", y_axis="R_total", title=str(self.user.airline) + " Total Revenue " + str(self.user.start_year)
            )
            plt.show()

            # 1.1.5 Total pax (year/ month)
            # (I have only prepared a version sorted by calendar month for now)
            plt.figure(figsize=(12, 6))
            self.plot_total_pax = self.bar_plot_yearmonth_sum(
                x_axis="Year-Month", y_axis="Passengers", title=str(self.user.airline) + " Total Passengers " + str(self.user.start_year)
            )
            plt.show()

            # 1.1.6 Average Load factor (year / month)
            plt.figure(figsize=(12, 6))
            self.plot_loadfactor = self.line_plot_yearmonth_loadfactor(
                x_axis="Year-Month",
                title=str(self.user.airline) + " Load Factor " + str(self.user.start_year),
                hue_col="Airport Pair",
                marker="o",
            )
            plt.show()

            # 1.1.7 Rask Analysis by Route (single year)
            plt.figure(figsize=(12, 6))
            self.plot_rask = self.line_plot_yearmonth_sum(
                x_axis="Year-Month",
                y_axis="RASK",
                title=str(self.user.airline)
                + " RASK analysis by route "
                + str(self.user.start_year),
                hue_col="Airport Pair",
                marker="o",
            )
            plt.show()

            # 1.1.8 Net Yield by Route (year/month)
            plt.figure()
            self.plot_net_yield = self.bar_plot_yearavg(
                x_axis="Airport Pair",
                y_axis="Yield_net",
                title=str(self.user.airline) + " Net Yield by Route in year(s) "
                + str(self.user.start_year)
                + "-"
                + str(self.user.end_year),
            )
            plt.show()

        # Prepare base plots
        def _prep_yearmonth(self, df_plot):  # For year-month plots
            df_plot = df_plot.copy()
            df_plot["Year-Month"] = pd.to_datetime(
                df_plot[["Year", "Month"]].assign(Day=1)
            )
            df_plot = df_plot.sort_values("Year-Month")
            df_plot["Year-Month"] = df_plot["Year-Month"].dt.strftime("%Y-%m")
            return df_plot

        def _base_plot_yearavg(
            self, plot_func, x_axis, y_axis, title=None, hue_col=None, **kwargs
        ):

            group_cols = (
                [x_axis] if hue_col is None else [x_axis, hue_col]
            )  # Flexibility for plots with or without hue_col
            df_plot_sorted = (
                self.df_sliced.groupby(group_cols)[y_axis].mean().reset_index()
            )  # I have put this code here instead of _merge() in case the not-averaged data is needed for other types of plots.
            df_plot_sorted = df_plot_sorted.sort_values(y_axis, ascending=False)

            if plot_func == sns.barplot:
                plot_func(
                    data=df_plot_sorted,
                    x=x_axis,
                    y=y_axis,
                    hue=hue_col,
                    order=df_plot_sorted[x_axis],
                    **kwargs,
                )
            else:
                plot_func(
                    data=df_plot_sorted, x=x_axis, y=y_axis, hue=hue_col, **kwargs
                )

            self._format_plot(title, x_axis, y_axis, hue_col)

            return plt.gcf()

        def _base_plot_yearmonth_sum(
            self, plot_func, x_axis, y_axis, title=None, hue_col=None, **kwargs
        ):

            group_cols = (
                ["Year", "Month"] if hue_col is None else ["Year", "Month", hue_col]
            )
            df_plot_yearmonth = (
                self.df_sliced.groupby(group_cols)[y_axis].sum().reset_index()
            )
            df_plot_yearmonth = self._prep_yearmonth(df_plot_yearmonth)

            if plot_func == sns.barplot:
                plot_func(
                    data=df_plot_yearmonth,
                    x=x_axis,
                    y=y_axis,
                    hue=hue_col,
                    order=df_plot_yearmonth[x_axis],
                    **kwargs,
                )
            else:
                plot_func(
                    data=df_plot_yearmonth, x=x_axis, y=y_axis, hue=hue_col, **kwargs
                )

            self._format_plot(title, "Year-Month", y_axis, hue_col)

            return plt.gcf()

        def _base_plot_yearmonth_loadfactor(
            self, plot_func, x_axis, title=None, hue_col=None, **kwargs
        ):

            group_cols = (
                ["Year", "Month"] if hue_col is None else ["Year", "Month", hue_col]
            )
            df_plot = (
                self.df_sliced.groupby(group_cols)
                .agg(
                    Total_Passengers=("Passengers", "sum"),
                    Total_Seats=("Seats (Total)", "sum"),
                )
                .reset_index()
            )

            df_plot["Load_Factor"] = (
                df_plot["Total_Passengers"] / df_plot["Total_Seats"]
            )
            df_plot = self._prep_yearmonth(df_plot)

            plot_func(data=df_plot, x=x_axis, y="Load_Factor", hue=hue_col, **kwargs)

            self._format_plot(title, x_axis, "Load Factor", hue_col)

            return plt.gcf()

        def _format_plot(self, title, x_axis, y_axis, hue_col):
            plt.title(str(title)) if title is not None else None
            plt.xlabel(str(x_axis))
            plt.ylabel(str(y_axis))
            plt.legend(
                title=str(self.user.airline), loc="lower left", bbox_to_anchor=(1, 0)
            ) if hue_col is not None else None

        # public plotting methods

        def bar_plot_yearavg(self, x_axis, y_axis, title=None, hue_col=None, **kwargs):
            return self._base_plot_yearavg(
                sns.barplot, x_axis, y_axis, title, hue_col, **kwargs
            )

        def line_plot_yearmonth_sum(
            self, x_axis, y_axis, title=None, hue_col=None, **kwargs
        ):
            return self._base_plot_yearmonth_sum(
                sns.lineplot, x_axis, y_axis, title, hue_col, **kwargs
            )

        def bar_plot_yearmonth_sum(
            self, x_axis, y_axis, title=None, hue_col=None, **kwargs
        ):
            return self._base_plot_yearmonth_sum(
                sns.barplot, x_axis, y_axis, title, hue_col, **kwargs
            )

        def line_plot_yearmonth_loadfactor(
            self, x_axis, title=None, hue_col=None, **kwargs
        ):
            return self._base_plot_yearmonth_loadfactor(
                sns.lineplot, x_axis, title, hue_col, **kwargs
            )

    sq_user = User(airline="SQ", start_year=2019)
    sq_basic_analysis = Revenue_Analysis(
        user=sq_user, df1=gy, df2=df, df2_cols=["D_trunk", "Airport Pair", "City Pair"]
    )

    mh_user = User(airline="MH", start_year=2019)
    mh_basic_analysis = Revenue_Analysis(
        user=mh_user, df1=gy, df2=df, df2_cols=["D_trunk", "Airport Pair", "City Pair"]
    )



    #reb_data.paper2_preprocess()
    #sea_reb_calculator = RebCalculator(reb_data)
    #df, gy, re, reb = sea_reb_calculator.calculate_reb()
    #reb_plotter = RebPlotter(df, gy, re, reb, reb_data)
    #reb_plotter.plot_city_pairs()

    en = time.time()
    print(f"Time taken: {en - st}")
    print()
    
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


if __name__ == "__main__":
    template()
    print()
    print("Sunny was here.")

# Sunny was here
# Sunny is here again and ready to push to origin.
# Let's do it again