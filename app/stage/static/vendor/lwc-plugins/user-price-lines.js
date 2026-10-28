// ../lwc-repo/plugin-examples/src/plugins/user-price-lines/user-price-lines.ts
import {
  CrosshairMode,
  LineStyle
} from "lightweight-charts";

// ../lwc-repo/packages/lwc-toolkit/src/dimensions/positions.ts
function centreOffset(lineBitmapWidth) {
  return Math.floor(lineBitmapWidth * 0.5);
}
function positionsLine(positionMedia, pixelRatio, desiredWidthMedia = 1, widthIsBitmap) {
  const scaledPosition = Math.round(pixelRatio * positionMedia);
  const lineBitmapWidth = widthIsBitmap ? desiredWidthMedia : Math.round(desiredWidthMedia * pixelRatio);
  const offset = centreOffset(lineBitmapWidth);
  const position = scaledPosition - offset;
  return { position, length: lineBitmapWidth };
}
function positionsBox(position1Media, position2Media, pixelRatio) {
  const scaledPosition1 = Math.round(pixelRatio * position1Media);
  const scaledPosition2 = Math.round(pixelRatio * position2Media);
  return {
    position: Math.min(scaledPosition1, scaledPosition2),
    length: Math.abs(scaledPosition2 - scaledPosition1) + 1
  };
}

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

// ../lwc-repo/plugin-examples/src/plugins/user-price-lines/user-price-lines.ts
var LABEL_HEIGHT = 21;
var plusIcon = `M7.5,7.5 m -7,0 a 7,7 0 1,0 14,0 a 7,7 0 1,0 -14,0 M4 7.5H11 M7.5 4V11`;
var plusIconPath = new Path2D(plusIcon);
var plusIconSize = 15;
var UserPriceLineDataBase = class {
  _y = 0;
  _data;
  constructor(data) {
    this._data = data;
  }
  update(data, series) {
    this._data = data;
    if (!this._data.price) {
      this._y = -1e4;
      return;
    }
    this._y = series.priceToCoordinate(this._data.price) ?? -1e4;
  }
};
var UserPriceLinesPaneRenderer = class {
  _data;
  constructor(data) {
    this._data = data;
  }
  draw(target) {
    if (!this._data.visible) return;
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const height = LABEL_HEIGHT;
      const width = height + 1;
      const xPos = positionsBox(this._data.rightX - width, this._data.rightX - 1, scope.horizontalPixelRatio);
      const yPos = positionsLine(this._data.y, scope.verticalPixelRatio, height);
      ctx.fillStyle = this._data.color;
      const roundedArray = [5, 0, 0, 5].map((i) => i * scope.horizontalPixelRatio);
      ctx.beginPath();
      ctx.roundRect(xPos.position, yPos.position, xPos.length, yPos.length, roundedArray);
      ctx.fill();
      if (this._data.hovered) {
        ctx.fillStyle = this._data.hoverColor;
        ctx.beginPath();
        ctx.roundRect(xPos.position, yPos.position, xPos.length, yPos.length, roundedArray);
        ctx.fill();
      }
      ctx.translate(xPos.position + 3 * scope.horizontalPixelRatio, yPos.position + 3 * scope.verticalPixelRatio);
      ctx.scale(scope.horizontalPixelRatio, scope.verticalPixelRatio);
      const iconScaling = 15 / plusIconSize;
      ctx.scale(iconScaling, iconScaling);
      ctx.strokeStyle = this._data.textColor;
      ctx.lineWidth = 1;
      ctx.stroke(plusIconPath);
    });
  }
};
var UserPriceLinesPaneView = class extends UserPriceLineDataBase {
  renderer() {
    const color = this._data.crosshairColor;
    return new UserPriceLinesPaneRenderer({
      visible: this._data.visible,
      y: this._y,
      color,
      textColor: this._data.crosshairLabelColor,
      rightX: this._data.timeScaleWidth,
      hoverColor: this._data.hoverColor,
      hovered: this._data.hovered ?? false
    });
  }
  zOrder() {
    return "top";
  }
};
var UserPriceLinesLabelButton = class extends PluginBase {
  _paneViews;
  _data = {
    visible: false,
    hovered: false,
    timeScaleWidth: 0,
    crosshairLabelColor: "#000000",
    crosshairColor: "#ffffff",
    lineColor: "#000000",
    hoverColor: "#777777"
  };
  _source;
  constructor(source) {
    super();
    this._paneViews = [new UserPriceLinesPaneView(this._data)];
    this._source = source;
  }
  updateAllViews() {
    this._paneViews.forEach((pw) => pw.update(this._data, this.series));
  }
  priceAxisViews() {
    return [];
  }
  paneViews() {
    return this._paneViews;
  }
  showAddLabel(price, hovered) {
    const crosshairColor = this.chart.options().crosshair.horzLine.labelBackgroundColor;
    this._data = {
      visible: true,
      price,
      hovered,
      timeScaleWidth: this.chart.timeScale().width(),
      crosshairColor,
      crosshairLabelColor: "#FFFFFF",
      lineColor: this._source.currentLineColor(),
      hoverColor: this._source.currentHoverColor()
    };
    this.updateAllViews();
    this.requestUpdate();
  }
  hideAddLabel() {
    this._data.visible = false;
    this.updateAllViews();
    this.requestUpdate();
  }
};
var defaultOptions = {
  color: "#000000",
  hoverColor: "#777777",
  limitToOne: true
};
var UserPriceLines = class {
  _chart;
  _series;
  _options;
  _labelButtonPrimitive;
  constructor(chart, series, options) {
    this._chart = chart;
    this._series = series;
    this._options = {
      ...defaultOptions,
      ...options
    };
    this._chart.subscribeClick(this._clickHandler);
    this._chart.subscribeCrosshairMove(this._moveHandler);
    this._labelButtonPrimitive = new UserPriceLinesLabelButton(this);
    series.attachPrimitive(this._labelButtonPrimitive);
    this._setCrosshairMode();
  }
  currentLineColor() {
    return this._options.color;
  }
  currentHoverColor() {
    return this._options.hoverColor;
  }
  // We need to disable magnet mode for this to work nicely
  _setCrosshairMode() {
    if (!this._chart) {
      throw new Error(
        "Unable to change crosshair mode because the chart instance is undefined"
      );
    }
    this._chart.applyOptions({
      crosshair: {
        mode: CrosshairMode.Normal
      }
    });
  }
  _clickHandler = (param) => this._onClick(param);
  _moveHandler = (param) => this._onMouseMove(param);
  remove() {
    if (this._chart) {
      this._chart.unsubscribeClick(this._clickHandler);
      this._chart.unsubscribeCrosshairMove(this._moveHandler);
    }
    if (this._series && this._labelButtonPrimitive) {
      this._series.detachPrimitive(this._labelButtonPrimitive);
    }
    this._chart = void 0;
    this._series = void 0;
  }
  _onClick(param) {
    const price = this._getMousePrice(param);
    const xDistance = this._distanceFromRightScale(param);
    if (price === null || xDistance === null || xDistance > LABEL_HEIGHT || !this._series)
      return;
    this._series.createPriceLine({
      price,
      color: this._options.color,
      lineStyle: LineStyle.Dashed
    });
  }
  _onMouseMove(param) {
    const price = this._getMousePrice(param);
    const xDistance = this._distanceFromRightScale(param);
    if (price === null || xDistance === null || xDistance > LABEL_HEIGHT * 2) {
      this._labelButtonPrimitive.hideAddLabel();
      return;
    }
    this._labelButtonPrimitive.showAddLabel(price, xDistance < LABEL_HEIGHT);
  }
  _getMousePrice(param) {
    if (!param.point || !this._series) return null;
    const price = this._series.coordinateToPrice(param.point.y);
    return price;
  }
  _distanceFromRightScale(param) {
    if (!param.point || !this._chart) return null;
    const timeScaleWidth = this._chart.timeScale().width();
    return Math.abs(timeScaleWidth - param.point.x);
  }
};
export {
  UserPriceLines
};
