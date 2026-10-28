// ../lwc-repo/packages/lwc-toolkit/src/assertions.ts
function ensureDefined(value) {
  if (value === void 0) {
    throw new Error("Value is undefined");
  }
  return value;
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

// ../lwc-repo/plugin-examples/src/plugins/session-highlighting/session-highlighting.ts
var SessionHighlightingPaneRenderer = class {
  _viewData;
  constructor(data) {
    this._viewData = data;
  }
  draw(target) {
    const points = this._viewData.data;
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const yTop = 0;
      const height = scope.bitmapSize.height;
      const halfWidth = scope.horizontalPixelRatio * this._viewData.barWidth / 2;
      const cutOff = -1 * (halfWidth + 1);
      const maxX = scope.bitmapSize.width;
      points.forEach((point) => {
        const xScaled = point.x * scope.horizontalPixelRatio;
        if (xScaled < cutOff) return;
        ctx.fillStyle = point.color || "rgba(0, 0, 0, 0)";
        const x1 = Math.max(0, Math.round(xScaled - halfWidth));
        const x2 = Math.min(maxX, Math.round(xScaled + halfWidth));
        ctx.fillRect(x1, yTop, x2 - x1, height);
      });
    });
  }
};
var SessionHighlightingPaneView = class {
  _source;
  _data;
  constructor(source) {
    this._source = source;
    this._data = {
      data: [],
      barWidth: 6,
      options: this._source._options
    };
  }
  update() {
    const timeScale = this._source.chart.timeScale();
    this._data.data = this._source._backgroundColors.map((d) => {
      return {
        x: timeScale.timeToCoordinate(d.time) ?? -100,
        color: d.color
      };
    });
    if (this._data.data.length > 1) {
      this._data.barWidth = this._data.data[1].x - this._data.data[0].x;
    } else {
      this._data.barWidth = 6;
    }
  }
  renderer() {
    return new SessionHighlightingPaneRenderer(this._data);
  }
  zOrder() {
    return "bottom";
  }
};
var defaults = {};
var SessionHighlighting = class extends PluginBase {
  _paneViews;
  _seriesData = [];
  _backgroundColors = [];
  _options;
  _highlighter;
  constructor(highlighter, options = {}) {
    super();
    this._highlighter = highlighter;
    this._options = { ...defaults, ...options };
    this._paneViews = [new SessionHighlightingPaneView(this)];
  }
  updateAllViews() {
    this._paneViews.forEach((pw) => pw.update());
  }
  paneViews() {
    return this._paneViews;
  }
  attached(p) {
    super.attached(p);
    this.dataUpdated("full");
  }
  dataUpdated(_scope) {
    this._backgroundColors = this.series.data().map((dataPoint) => {
      return {
        time: dataPoint.time,
        color: this._highlighter(dataPoint.time)
      };
    });
    this.requestUpdate();
  }
};
export {
  SessionHighlighting
};
