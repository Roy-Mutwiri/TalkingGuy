// ../lwc-repo/packages/lwc-toolkit/src/dimensions/positions.ts
function positionsBox(position1Media, position2Media, pixelRatio) {
  const scaledPosition1 = Math.round(pixelRatio * position1Media);
  const scaledPosition2 = Math.round(pixelRatio * position2Media);
  return {
    position: Math.min(scaledPosition1, scaledPosition2),
    length: Math.abs(scaledPosition2 - scaledPosition1) + 1
  };
}

// ../lwc-repo/plugin-examples/src/plugins/volume-profile/volume-profile.ts
var VolumeProfileRenderer = class {
  _data;
  constructor(data) {
    this._data = data;
  }
  draw(target) {
    target.useBitmapCoordinateSpace((scope) => {
      if (this._data.x === null || this._data.top === null) return;
      const ctx = scope.context;
      const horizontalPositions = positionsBox(
        this._data.x,
        this._data.x + this._data.width,
        scope.horizontalPixelRatio
      );
      const verticalPositions = positionsBox(
        this._data.top,
        this._data.top - this._data.columnHeight * this._data.items.length,
        scope.verticalPixelRatio
      );
      ctx.fillStyle = "rgba(0, 0, 255, 0.2)";
      ctx.fillRect(
        horizontalPositions.position,
        verticalPositions.position,
        horizontalPositions.length,
        verticalPositions.length
      );
      ctx.fillStyle = "rgba(80, 80, 255, 0.8)";
      this._data.items.forEach((row) => {
        if (row.y === null) return;
        const itemVerticalPos = positionsBox(
          row.y,
          row.y - this._data.columnHeight,
          scope.verticalPixelRatio
        );
        const itemHorizontalPos = positionsBox(
          this._data.x,
          this._data.x + row.width,
          scope.horizontalPixelRatio
        );
        ctx.fillRect(
          itemHorizontalPos.position,
          itemVerticalPos.position,
          itemHorizontalPos.length,
          itemVerticalPos.length - 2
          // 1 to close gaps
        );
      });
    });
  }
};
var VolumeProfilePaneView = class {
  _source;
  _x = null;
  _width = 6;
  _columnHeight = 0;
  _top = null;
  _items = [];
  constructor(source) {
    this._source = source;
  }
  update() {
    const data = this._source._vpData;
    const series = this._source._series;
    const timeScale = this._source._chart.timeScale();
    this._x = timeScale.timeToCoordinate(data.time);
    this._width = timeScale.options().barSpacing * data.width;
    const y1 = series.priceToCoordinate(data.profile[0].price) ?? 0;
    const y2 = series.priceToCoordinate(data.profile[1].price) ?? timeScale.height();
    this._columnHeight = Math.max(1, y1 - y2);
    const maxVolume = data.profile.reduce(
      (acc, item) => Math.max(acc, item.vol),
      0
    );
    this._top = y1;
    this._items = data.profile.map((row) => ({
      y: series.priceToCoordinate(row.price),
      width: this._width * row.vol / maxVolume
    }));
  }
  renderer() {
    return new VolumeProfileRenderer({
      x: this._x,
      top: this._top,
      columnHeight: this._columnHeight,
      width: this._width,
      items: this._items
    });
  }
};
var VolumeProfile = class {
  _chart;
  _series;
  _vpData;
  _minPrice;
  _maxPrice;
  _paneViews;
  _vpIndex = null;
  constructor(chart, series, vpData) {
    this._chart = chart;
    this._series = series;
    this._vpData = vpData;
    this._minPrice = Infinity;
    this._maxPrice = -Infinity;
    this._vpData.profile.forEach((vpData2) => {
      if (vpData2.price < this._minPrice) this._minPrice = vpData2.price;
      if (vpData2.price > this._maxPrice) this._maxPrice = vpData2.price;
    });
    this._paneViews = [new VolumeProfilePaneView(this)];
  }
  updateAllViews() {
    this._paneViews.forEach((pw) => pw.update());
  }
  // Ensures that the VP is within autoScale
  autoscaleInfo(startTimePoint, endTimePoint) {
    const vpCoordinate = this._chart.timeScale().timeToCoordinate(this._vpData.time);
    if (vpCoordinate === null) return null;
    const vpIndex = this._chart.timeScale().coordinateToLogical(vpCoordinate);
    if (vpIndex === null) return null;
    if (endTimePoint < vpIndex || startTimePoint > vpIndex + this._vpData.width)
      return null;
    return {
      priceRange: {
        minValue: this._minPrice,
        maxValue: this._maxPrice
      }
    };
  }
  paneViews() {
    return this._paneViews;
  }
};
export {
  VolumeProfile
};
