import { parse } from "csv-parse/sync";
import fs from "fs";

export default function (eleventyConfig) {
  eleventyConfig.setInputDirectory("src");
  eleventyConfig.addPassthroughCopy("assets");
  eleventyConfig.setIncludesDirectory("_includes");
  eleventyConfig.setOutputDirectory("_site");
  
  eleventyConfig.addDataExtension("csv", (contents) => {
    const records = parse(contents, {
      columns: true,
      skip_empty_lines: true,
    });
    // Convert ID and *ID columns to integers
    return records.map(record => {
      const converted = { ...record };
      for (const key in converted) {
        if (key.endsWith('ID') || key === 'ID') {
          converted[key] = parseInt(converted[key], 10);
        }
      }
      return converted;
    });
  });

  // add a simple sortBy filter for Nunjucks templates
  eleventyConfig.addNunjucksFilter("sortBy", (arr, key) => {
    if (!Array.isArray(arr)) return arr;
    return [...arr].sort((a, b) => {
      const A = String(key ? (a?.[key]) : a ?? "").toLowerCase();
      const B = String(key ? (b?.[key]) : b ?? "").toLowerCase();
      return A.localeCompare(B);
    });
  });
}