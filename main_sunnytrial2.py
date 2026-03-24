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
    reb_data.paper2_preprocess()
    sea_reb_calculator = RebCalculator(reb_data)
    df, gy, re, reb = sea_reb_calculator.calculate_reb()
    # reb_plotter = RebPlotter(df, gy, re, reb, reb_data)
    # reb_plotter.plot_city_pairs()

    # Sunny's analysis here

    import seaborn as sns
    import pandas as pd
    import matplotlib.pyplot as plt

    class User:
        def __init__(self, airline, start_year, end_year=None):
            self.airline = airline
            self.start_year = start_year
            self.end_year = end_year if end_year is not None else start_year

    class RevenueAnalysis:
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

        # Step 1: merge and slice dataframes
        def _merge(self):
            if self.df2 is not None and self.df2_cols is not None:
                df2_deduped = self.df2[
                    ["Leg Origin Airport", "Leg Destination Airport"] + self.df2_cols
                ].drop_duplicates(
                    subset=["Leg Origin Airport", "Leg Destination Airport"]
                )
                df_merged = self.df1.merge(
                    df2_deduped,
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

        # data aggregation by year-month
        def _prep_yearmonth(self, df_plot):  # For year-month plots
            df_plot = df_plot.copy()
            df_plot["Year-Month"] = pd.to_datetime(
                df_plot[["Year", "Month"]].assign(Day=1)
            )
            df_plot = df_plot.sort_values("Year-Month")
            df_plot["Year-Month"] = df_plot["Year-Month"].dt.strftime("%Y-%m")
            return df_plot

        def get_sum_by_yearmonth(self, col, group_by=None):

            group_cols = (
                ["Year", "Month"] if group_by is None else ["Year", "Month", group_by]
            )
            df_plot_yearmonth = (
                self.df_sliced.groupby(group_cols)[col].sum().reset_index()
            )
            df_plot_yearmonth = self._prep_yearmonth(df_plot_yearmonth)
            return df_plot_yearmonth

        # Data by year average on key
        def get_avg_by_year(self, key, col, group_by=None):
            group_cols = [key] if group_by is None else [key, group_by]
            df_plot_avg_by_year = (
                self.df_sliced.groupby(group_cols)[col].mean().reset_index()
            )
            df_plot_avg_by_year = df_plot_avg_by_year.sort_values(
                col, ascending=False
            )  
            return df_plot_avg_by_year

        # Special method for calculating load factor (average by year-month)
        def avg_load_factor_yearmonth(self, group_by=None):
            group_cols = (
                ["Year", "Month"] if group_by is None else ["Year", "Month", group_by]
            )
            df_avg_loadfactor_ym = (
                self.df_sliced.groupby(group_cols)
                .agg(
                    Total_Passengers=("Passengers", "sum"),
                    Total_Seats=("Seats (Total)", "sum"),
                )
                .reset_index()
            )
            df_avg_loadfactor_ym["Load Factor"] = (
                df_avg_loadfactor_ym["Total_Passengers"]
                / df_avg_loadfactor_ym["Total_Seats"]
            )
            df_avg_loadfactor_ym = self._prep_yearmonth(df_avg_loadfactor_ym)
            return df_avg_loadfactor_ym

        # Step 2: analyses
        # 1.1.1 General stats

        def general_stats(self):

            no_of_routes = self.df_sliced["Airport Pair"].nunique()
            no_of_destinations = self.df_sliced["Leg Destination Airport"].nunique()
            no_of_pax = self.df_sliced["Passengers"].sum()
            total_revenue = self.df_sliced["R_total"].sum()
            total_seats = self.df_sliced["Seats (Total)"].sum()
            load_factor = no_of_pax / total_seats
            return (
                no_of_routes,
                no_of_destinations,
                no_of_pax,
                total_revenue,
                total_seats,
                load_factor,
            )

        # 1.1.2 Top ten destinations by revenue (single airline, selected year/year avg)

        def top_ten_revenue(self):

            df_grouped = (
                self.df_sliced.groupby("Airport Pair")["R_total"]
                .sum()
                .reset_index()
                .sort_values("R_total", ascending=False)
                .reset_index(drop=True)
            )
            return df_grouped.head(10)

        # 1.1.3 Top ten destination by passenger numbers (single airline, selected year/year avg)

        def top_ten_pax(self):

            df_grouped = (
                self.df_sliced.groupby("Airport Pair")["Passengers"]
                .sum()
                .reset_index()
                .sort_values("Passengers", ascending=False)
                .reset_index(drop=True)
            )
            return df_grouped.head(10)

        # 1.1.4 Total revenue (year/ month)
        # 1.1.5 Total pax (year/ month)
        # 1.1.6 Average Load factor (year / month)
        # 1.1.7 Rask Analysis by Route (single year)
        # 1.1.8 Net Yield by Route (year/month)

    class GraphPlotting:
        def __init__(self, analysis):
            self.analysis = analysis

        # to make all plots on instantiation:
        def plot_all(self):
            print(self.plot_genstat())  # 1.1.1
            print(self.plot_top10_revenue())  # 1.1.2
            print(self.plot_top10_pax())  # 1.1.3
            self.plot_total_revenue()  # 1.1.4
            self.plot_total_pax()  # 1.1.5
            self.plot_avg_load_factor()  # 1.1.6
            self.rask_by_route()  # 1.1.7
            self.net_yield_by_route()  # 1.1.8

        # Prepare base plots
        def _base_plot(
            self, df, plot_func, x_axis, y_axis, title=None, hue_col=None, **kwargs
        ):
            if plot_func == sns.barplot:
                plot_func(
                    data=df,
                    x=x_axis,
                    y=y_axis,
                    hue=hue_col,
                    order=df[x_axis],
                    **kwargs,
                )
            else:
                plot_func(data=df, x=x_axis, y=y_axis, hue=hue_col, **kwargs)

            self._format_plot(title, x_axis, y_axis, hue_col)

            return plt.gcf()

        def _format_plot(self, title, x_axis, y_axis, hue_col):
            plt.title(str(title)) if title is not None else None
            plt.xlabel(str(x_axis))
            plt.ylabel(str(y_axis))
            plt.legend(
                title=str(self.analysis.user.airline),
                loc="lower left",
                bbox_to_anchor=(1, 0),
            ) if hue_col is not None else None

        # public plotting methods
        # Printing top 10 (generic)

        def print_top10(self, df, key_col, value_col, title, prefix="", suffix=""):
            header = f"""
                {"=" * 40}
                {self.analysis.user.airline} {self.analysis.user.start_year} {title}
                {"=" * 40}
            """

            rows = ""
            for i in range(min(10, len(df))):
                key = df.loc[i, key_col]
                value = df.loc[i, value_col]
                rows += f"""
                {i + 1}. {key}: {prefix}{value:,.0f}{suffix}"""

            return header + rows

        def bar_plot_yearavg(self, x_axis, y_axis, title=None, hue_col=None, **kwargs):
            df = self.analysis.get_avg_by_year(key=x_axis, col=y_axis, group_by=hue_col)
            return self._base_plot(
                df=df,
                plot_func=sns.barplot,
                x_axis=x_axis,
                y_axis=y_axis,
                title=title,
                hue_col=hue_col,
                **kwargs,
            )

        def line_plot_yearmonth_sum(self, col, title=None, hue_col=None, **kwargs):
            df = self.analysis.get_sum_by_yearmonth(col, group_by=hue_col)
            return self._base_plot(
                df=df,
                plot_func=sns.lineplot,
                x_axis="Year-Month",
                y_axis=col,
                title=title,
                hue_col=hue_col,
                **kwargs,
            )

        def bar_plot_yearmonth_sum(self, col, title=None, hue_col=None, **kwargs):
            df = self.analysis.get_sum_by_yearmonth(col, group_by=hue_col)
            return self._base_plot(
                df=df,
                plot_func=sns.barplot,
                x_axis="Year-Month",
                y_axis=col,
                title=title,
                hue_col=hue_col,
                **kwargs,
            )

        def line_plot_yearmonth_loadfactor(
            self, col, title=None, hue_col=None, **kwargs
        ):
            df = self.analysis.avg_load_factor_yearmonth(group_by=hue_col)
            return self._base_plot(
                df=df,
                plot_func=sns.lineplot,
                x_axis="Year-Month",
                y_axis=col,
                title=title,
                hue_col=hue_col,
                **kwargs,
            )

        # 1.1.1 Printing general stats

        def plot_genstat(self):
            (
                no_of_routes,
                no_of_destinations,
                no_of_pax,
                total_revenue,
                total_seats,
                load_factor,
            ) = self.analysis.general_stats()

            summary = f"""
                {"=" * 40}
                {self.analysis.user.airline} {self.analysis.user.start_year} Performance Summary
                {"=" * 40}
                Total number of routes:         {no_of_routes}
                Total number of destinations:   {no_of_destinations}
                Total number of passengers:     {no_of_pax:,.0f}
                Total revenue:                  {total_revenue:,.0f}
                Average load factor:            {load_factor:,.2%}
                {"=" * 40}
                """
            return summary

        # 1.1.2 Top ten destinations by revenue
        def plot_top10_revenue(self):
            df = self.analysis.top_ten_revenue()
            return self.print_top10(
                df,
                "Airport Pair",
                "R_total",
                "Top 10 destinations by revenue",
                prefix="$",
            )

        # 1.1.3 Top ten destinations by passenger numbers
        def plot_top10_pax(self):
            df = self.analysis.top_ten_pax()
            return self.print_top10(
                df,
                "Airport Pair",
                "Passengers",
                "Top 10 destinations by number of passengers",
            )

        # 1.1.4 Total revenue (year/month)
        def plot_total_revenue(self):
            plt.figure(figsize=(12, 6))
            self.line_plot_yearmonth_sum(
                col="R_total",
                title=f"{self.analysis.user.airline} Total Revenue {self.analysis.user.start_year}",
            )
            plt.show()

        # 1.1.5 Total pax (year/month)
        def plot_total_pax(self):
            plt.figure(figsize=(12, 6))
            self.bar_plot_yearmonth_sum(
                col="Passengers",
                title=f"{self.analysis.user.airline} Total Passengers {self.analysis.user.start_year}",
            )
            plt.show()

        # 1.1.6 Average Load factor (year / month)
        def plot_avg_load_factor(self):
            plt.figure(figsize=(12, 6))
            self.line_plot_yearmonth_loadfactor(
                col="Load Factor",
                title=f"{self.analysis.user.airline} Load Factor {self.analysis.user.start_year}",
                hue_col="Airport Pair",
                marker="o",
            )
            plt.show()

        # 1.1.7 RASK Analysis by Route (single year)
        def rask_by_route(self):
            plt.figure(figsize=(12, 6))
            self.line_plot_yearmonth_sum(
                col="RASK",
                title=f"{self.analysis.user.airline} RASK analysis by route {self.analysis.user.start_year}",
                hue_col="Airport Pair",
                marker="o",
            )
            plt.show()

        # 1.1.8 Net Yield by Route (year/month)
        def net_yield_by_route(self):
            plt.figure(figsize=(12, 6))
            self.bar_plot_yearavg(
                x_axis="Airport Pair",
                y_axis="Yield_net",
                title=f"{self.analysis.user.airline} Net Yield by Route in year(s) {self.analysis.user.start_year}-{self.analysis.user.end_year}",
            )
            plt.show()

    class PlotAnalysis:
        def __init__(self, airline, start_year, end_year=None, df1=None, df2=None, df2_cols=None):
            self.user = User(airline=airline, start_year=start_year, end_year=end_year)
            self.analysis = RevenueAnalysis(user=self.user, df1=df1, df2=df2, df2_cols=df2_cols)
            self.graphs = GraphPlotting(analysis=self.analysis)
        
        def run(self):
            self.graphs.plot_all()


    sq = PlotAnalysis(airline="SQ", start_year=2019, df1=gy, df2=df, df2_cols=["D_trunk", "Airport Pair", "City Pair"])
    sq.run()
    
    mh = PlotAnalysis(airline="MH", start_year=2019, df1=gy, df2=df, df2_cols=["D_trunk", "Airport Pair", "City Pair"])
    mh.run()

    en = time.time()
    print(f"Time taken: {en - st}")
    print()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


if __name__ == "__main__":
    template()
    print()
    print("Sunny was here.")

# Sunny was here
# Sunny is here again and ready to push to origin.
# Let's do it again
