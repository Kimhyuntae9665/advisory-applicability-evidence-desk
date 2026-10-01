import {loadSources} from "../core.mjs";
if (!loadSources().length) throw new Error("Source records missing");
console.log("CPU startup and source integrity passed");
