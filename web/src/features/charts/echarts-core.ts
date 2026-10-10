/** Tree-shaken ECharts build (bar charts, SVG renderer). Loaded lazily by BarChart. */
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([BarChart, GridComponent, TooltipComponent, SVGRenderer]);

export { echarts };
