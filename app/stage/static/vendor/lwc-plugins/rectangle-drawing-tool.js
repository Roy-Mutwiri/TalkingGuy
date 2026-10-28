// ../lwc-repo/plugin-examples/src/plugins/rectangle-drawing-tool/rectangle-drawing-tool.ts
import {
  isBusinessDay
} from "lightweight-charts";

// ../lwc-repo/packages/lwc-toolkit/src/assertions.ts
function ensureDefined(value) {
  if (value === void 0) {
    throw new Error("Value is undefined");
  }
  return value;
}

// ../lwc-repo/packages/lwc-toolkit/src/dimensions/positions.ts
function positionsBox(position1Media, position2Media, pixelRatio) {
  const scaledPosition1 = Math.round(pixelRatio * position1Media);
  const scaledPosition2 = Math.round(pixelRatio * position2Media);
  return {
    position: Math.min(scaledPosition1, scaledPosition2),
    length: Math.abs(scaledPosition2 - scaledPosition1) + 1
  };
}

// ../lwc-repo/packages/lwc-toolkit/src/plugin-base.ts
var PluginBase = class {
  _chart = void 0;
  _series = void 0;
  requestUpdate() {
    if (this._requestUpdate) this._requestUpdate();
  }
  _requestUpdate;
  attached({ chart, series, requestUpdate }) {
    this._chart = chart;
    this._series = series;
    this._series.subscribeDataChanged(this._fireDataUpdated);
    this._requestUpdate = requestUpdate;
    this.requestUpdate();
  }
  detached() {
    this._series?.unsubscribeDataChanged(this._fireDataUpdated);
    this._chart = void 0;
    this._series = void 0;
    this._requestUpdate = void 0;
  }
  get chart() {
    return ensureDefined(this._chart);
  }
  get series() {
    return ensureDefined(this._series);
  }
  // This method is a class property to maintain the
  // lexical 'this' scope (due to the use of the arrow function)
  // and to ensure its reference stays the same, so we can unsubscribe later.
  _fireDataUpdated = (scope) => {
    if (this.dataUpdated) {
      this.dataUpdated(scope);
    }
  };
};

// ../lwc-repo/plugin-examples/src/plugins/rectangle-drawing-tool/rectangle-drawing-tool.ts
var RectanglePaneRenderer = class {
  _p1;
  _p2;
  _fillColor;
  constructor(p1, p2, fillColor) {
    this._p1 = p1;
    this._p2 = p2;
    this._fillColor = fillColor;
  }
  draw(target) {
    target.useBitmapCoordinateSpace((scope) => {
      if (this._p1.x === null || this._p1.y === null || this._p2.x === null || this._p2.y === null)
        return;
      const ctx = scope.context;
      const horizontalPositions = positionsBox(
        this._p1.x,
        this._p2.x,
        scope.horizontalPixelRatio
      );
      const verticalPositions = positionsBox(
        this._p1.y,
        this._p2.y,
        scope.verticalPixelRatio
      );
      ctx.fillStyle = this._fillColor;
      ctx.fillRect(
        horizontalPositions.position,
        verticalPositions.position,
        horizontalPositions.length,
        verticalPositions.length
      );
    });
  }
};
var RectanglePaneView = class {
  _source;
  _p1 = { x: null, y: null };
  _p2 = { x: null, y: null };
  constructor(source) {
    this._source = source;
  }
  update() {
    const series = this._source.series;
    const y1 = series.priceToCoordinate(this._source._p1.price);
    const y2 = series.priceToCoordinate(this._source._p2.price);
    const timeScale = this._source.chart.timeScale();
    const x1 = timeScale.timeToCoordinate(this._source._p1.time);
    const x2 = timeScale.timeToCoordinate(this._source._p2.time);
    this._p1 = { x: x1, y: y1 };
    this._p2 = { x: x2, y: y2 };
  }
  renderer() {
    return new RectanglePaneRenderer(
      this._p1,
      this._p2,
      this._source._options.fillColor
    );
  }
};
var RectangleAxisPaneRenderer = class {
  _p1;
  _p2;
  _fillColor;
  _vertical = false;
  constructor(p1, p2, fillColor, vertical) {
    this._p1 = p1;
    this._p2 = p2;
    this._fillColor = fillColor;
    this._vertical = vertical;
  }
  draw(target) {
    target.useBitmapCoordinateSpace((scope) => {
      if (this._p1 === null || this._p2 === null) return;
      const ctx = scope.context;
      ctx.globalAlpha = 0.5;
      const positions = positionsBox(
        this._p1,
        this._p2,
        this._vertical ? scope.verticalPixelRatio : scope.horizontalPixelRatio
      );
      ctx.fillStyle = this._fillColor;
      if (this._vertical) {
        ctx.fillRect(0, positions.position, 15, positions.length);
      } else {
        ctx.fillRect(positions.position, 0, positions.length, 15);
      }
    });
  }
};
var RectangleAxisPaneView = class {
  _source;
  _p1 = null;
  _p2 = null;
  _vertical = false;
  constructor(source, vertical) {
    this._source = source;
    this._vertical = vertical;
  }
  update() {
    [this._p1, this._p2] = this.getPoints();
  }
  renderer() {
    return new RectangleAxisPaneRenderer(
      this._p1,
      this._p2,
      this._source._options.fillColor,
      this._vertical
    );
  }
  zOrder() {
    return "bottom";
  }
};
var RectanglePriceAxisPaneView = class extends RectangleAxisPaneView {
  getPoints() {
    const series = this._source.series;
    const y1 = series.priceToCoordinate(this._source._p1.price);
    const y2 = series.priceToCoordinate(this._source._p2.price);
    return [y1, y2];
  }
};
var RectangleTimeAxisPaneView = class extends RectangleAxisPaneView {
  getPoints() {
    const timeScale = this._source.chart.timeScale();
    const x1 = timeScale.timeToCoordinate(this._source._p1.time);
    const x2 = timeScale.timeToCoordinate(this._source._p2.time);
    return [x1, x2];
  }
};
var RectangleAxisView = class {
  _source;
  _p;
  _pos = null;
  constructor(source, p) {
    this._source = source;
    this._p = p;
  }
  coordinate() {
    return this._pos ?? -1;
  }
  visible() {
    return this._source._options.showLabels;
  }
  tickVisible() {
    return this._source._options.showLabels;
  }
  textColor() {
    return this._source._options.labelTextColor;
  }
  backColor() {
    return this._source._options.labelColor;
  }
  movePoint(p) {
    this._p = p;
    this.update();
  }
};
var RectangleTimeAxisView = class extends RectangleAxisView {
  update() {
    const timeScale = this._source.chart.timeScale();
    this._pos = timeScale.timeToCoordinate(this._p.time);
  }
  text() {
    return this._source._options.timeLabelFormatter(this._p.time);
  }
};
var RectanglePriceAxisView = class extends RectangleAxisView {
  update() {
    const series = this._source.series;
    this._pos = series.priceToCoordinate(this._p.price);
  }
  text() {
    return this._source._options.priceLabelFormatter(this._p.price);
  }
};
var defaultOptions = {
  fillColor: "rgba(200, 50, 100, 0.75)",
  previewFillColor: "rgba(200, 50, 100, 0.25)",
  labelColor: "rgba(200, 50, 100, 1)",
  labelTextColor: "white",
  showLabels: true,
  priceLabelFormatter: (price) => price.toFixed(2),
  timeLabelFormatter: (time) => {
    if (typeof time == "string") return time;
    const date = isBusinessDay(time) ? new Date(time.year, time.month, time.day) : new Date(time * 1e3);
    return date.toLocaleDateString();
  }
};
var Rectangle = class extends PluginBase {
  _options;
  _p1;
  _p2;
  _paneViews;
  _timeAxisViews;
  _priceAxisViews;
  _priceAxisPaneViews;
  _timeAxisPaneViews;
  constructor(p1, p2, options = {}) {
    super();
    this._p1 = p1;
    this._p2 = p2;
    this._options = {
      ...defaultOptions,
      ...options
    };
    this._paneViews = [new RectanglePaneView(this)];
    this._timeAxisViews = [
      new RectangleTimeAxisView(this, p1),
      new RectangleTimeAxisView(this, p2)
    ];
    this._priceAxisViews = [
      new RectanglePriceAxisView(this, p1),
      new RectanglePriceAxisView(this, p2)
    ];
    this._priceAxisPaneViews = [new RectanglePriceAxisPaneView(this, true)];
    this._timeAxisPaneViews = [new RectangleTimeAxisPaneView(this, false)];
  }
  updateAllViews() {
    this._paneViews.forEach((pw) => pw.update());
    this._timeAxisViews.forEach((pw) => pw.update());
    this._priceAxisViews.forEach((pw) => pw.update());
    this._priceAxisPaneViews.forEach((pw) => pw.update());
    this._timeAxisPaneViews.forEach((pw) => pw.update());
  }
  priceAxisViews() {
    return this._priceAxisViews;
  }
  timeAxisViews() {
    return this._timeAxisViews;
  }
  paneViews() {
    return this._paneViews;
  }
  priceAxisPaneViews() {
    return this._priceAxisPaneViews;
  }
  timeAxisPaneViews() {
    return this._timeAxisPaneViews;
  }
  applyOptions(options) {
    this._options = { ...this._options, ...options };
    this.requestUpdate();
  }
};
var PreviewRectangle = class extends Rectangle {
  constructor(p1, p2, options = {}) {
    super(p1, p2, options);
    this._options.fillColor = this._options.previewFillColor;
  }
  updateEndPoint(p) {
    this._p2 = p;
    this._paneViews[0].update();
    this._timeAxisViews[1].movePoint(p);
    this._priceAxisViews[1].movePoint(p);
    this.requestUpdate();
  }
};
var RectangleDrawingTool = class {
  _chart;
  _series;
  _drawingsToolbarContainer;
  _defaultOptions;
  _rectangles;
  _previewRectangle = void 0;
  _points = [];
  _drawing = false;
  _toolbarButton;
  constructor(chart, series, drawingsToolbarContainer, options) {
    this._chart = chart;
    this._series = series;
    this._drawingsToolbarContainer = drawingsToolbarContainer;
    this._addToolbarButton();
    this._defaultOptions = options;
    this._rectangles = [];
    this._chart.subscribeClick(this._clickHandler);
    this._chart.subscribeCrosshairMove(this._moveHandler);
  }
  _clickHandler = (param) => this._onClick(param);
  _moveHandler = (param) => this._onMouseMove(param);
  remove() {
    this.stopDrawing();
    if (this._chart) {
      this._chart.unsubscribeClick(this._clickHandler);
      this._chart.unsubscribeCrosshairMove(this._moveHandler);
    }
    this._rectangles.forEach((rectangle) => {
      this._removeRectangle(rectangle);
    });
    this._rectangles = [];
    this._removePreviewRectangle();
    this._chart = void 0;
    this._series = void 0;
    this._drawingsToolbarContainer = void 0;
  }
  startDrawing() {
    this._drawing = true;
    this._points = [];
    if (this._toolbarButton) {
      this._toolbarButton.style.fill = "rgb(100, 150, 250)";
    }
  }
  stopDrawing() {
    this._drawing = false;
    this._points = [];
    if (this._toolbarButton) {
      this._toolbarButton.style.fill = "rgb(0, 0, 0)";
    }
  }
  isDrawing() {
    return this._drawing;
  }
  _onClick(param) {
    if (!this._drawing || !param.point || !param.time || !this._series) return;
    const price = this._series.coordinateToPrice(param.point.y);
    if (price === null) {
      return;
    }
    this._addPoint({
      time: param.time,
      price
    });
  }
  _onMouseMove(param) {
    if (!this._drawing || !param.point || !param.time || !this._series) return;
    const price = this._series.coordinateToPrice(param.point.y);
    if (price === null) {
      return;
    }
    if (this._previewRectangle) {
      this._previewRectangle.updateEndPoint({
        time: param.time,
        price
      });
    }
  }
  _addPoint(p) {
    this._points.push(p);
    if (this._points.length >= 2) {
      this._addNewRectangle(this._points[0], this._points[1]);
      this.stopDrawing();
      this._removePreviewRectangle();
    }
    if (this._points.length === 1) {
      this._addPreviewRectangle(this._points[0]);
    }
  }
  _addNewRectangle(p1, p2) {
    const rectangle = new Rectangle(p1, p2, { ...this._defaultOptions });
    this._rectangles.push(rectangle);
    ensureDefined(this._series).attachPrimitive(rectangle);
  }
  _removeRectangle(rectangle) {
    ensureDefined(this._series).detachPrimitive(rectangle);
  }
  _addPreviewRectangle(p) {
    this._previewRectangle = new PreviewRectangle(p, p, {
      ...this._defaultOptions
    });
    ensureDefined(this._series).attachPrimitive(this._previewRectangle);
  }
  _removePreviewRectangle() {
    if (this._previewRectangle) {
      ensureDefined(this._series).detachPrimitive(this._previewRectangle);
      this._previewRectangle = void 0;
    }
  }
  _addToolbarButton() {
    if (!this._drawingsToolbarContainer) return;
    const button = document.createElement("div");
    button.style.width = "20px";
    button.style.height = "20px";
    button.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path d="M315.4 15.5C309.7 5.9 299.2 0 288 0s-21.7 5.9-27.4 15.5l-96 160c-5.9 9.9-6.1 22.2-.4 32.2s16.3 16.2 27.8 16.2H384c11.5 0 22.2-6.2 27.8-16.2s5.5-22.3-.4-32.2l-96-160zM288 312V456c0 22.1 17.9 40 40 40H472c22.1 0 40-17.9 40-40V312c0-22.1-17.9-40-40-40H328c-22.1 0-40 17.9-40 40zM128 512a128 128 0 1 0 0-256 128 128 0 1 0 0 256z"/></svg>`;
    button.addEventListener("click", () => {
      if (this.isDrawing()) {
        this.stopDrawing();
      } else {
        this.startDrawing();
      }
    });
    this._drawingsToolbarContainer.appendChild(button);
    this._toolbarButton = button;
    const colorPicker = document.createElement("input");
    colorPicker.type = "color";
    colorPicker.value = "#C83264";
    colorPicker.style.width = "24px";
    colorPicker.style.height = "20px";
    colorPicker.style.border = "none";
    colorPicker.style.padding = "0px";
    colorPicker.style.backgroundColor = "transparent";
    colorPicker.addEventListener("change", () => {
      const newColor = colorPicker.value;
      this._defaultOptions.fillColor = newColor + "CC";
      this._defaultOptions.previewFillColor = newColor + "77";
      this._defaultOptions.labelColor = newColor;
    });
    this._drawingsToolbarContainer.appendChild(colorPicker);
  }
};
export {
  Rectangle,
  RectangleDrawingTool
};
