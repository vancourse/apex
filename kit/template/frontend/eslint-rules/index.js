import figureOnly from "./figure-only.js";
import noNullishDefault from "./no-nullish-default.js";
import noRawFetch from "./no-raw-fetch.js";
import requireDataControl from "./require-data-control.js";

export default {
  meta: { name: "local" },
  rules: {
    "figure-only": figureOnly,
    "no-nullish-default": noNullishDefault,
    "no-raw-fetch": noRawFetch,
    "require-data-control": requireDataControl,
  },
};
