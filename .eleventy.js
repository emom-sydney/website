import { parse } from "csv-parse/sync";
import fs from "fs";
import { feedPlugin } from "@11ty/eleventy-plugin-rss";

export default function (eleventyConfig) {
  eleventyConfig.setInputDirectory("src");
  eleventyConfig.addPassthroughCopy("assets");
  eleventyConfig.setIncludesDirectory("_includes");
  eleventyConfig.setOutputDirectory("_site");
  
  // csv handling: parse CSV files into arrays of objects
  eleventyConfig.addDataExtension("csv", (contents) => {
    const records = parse(contents, {
      columns: true,
      skip_empty_lines: true,
    });
    // the parser returns strings, so we convert 'ID' columns to integers
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

  // add a slugify filter to convert artist names to URL-safe slugs
  eleventyConfig.addNunjucksFilter("slugify", (str) => {
    return String(str)
      .toLowerCase()
      .trim()
      .replace(/[^\w\s-]/g, '')
      .replace(/[\s_]+/g, '-')
      .replace(/^-+|-+$/g, '');
  });

  // add a dateFilter for formatting blog post dates
  eleventyConfig.addNunjucksFilter("dateFilter", (date) => {
    if (!date) return "";
    const d = new Date(date);
    return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  });

  // create a collection for blog posts (sorted by date, newest first)
  eleventyConfig.addCollection("posts", (collection) => {
    return collection.getFilteredByGlob("src/posts/*.md").sort((a, b) => b.date - a.date);
  });

  // RSS feed plugin
  eleventyConfig.addPlugin(feedPlugin, {
  type: "atom", // or "rss", "json"
  outputPath: "/feed.xml",
  collection: {
    name: "posts", // iterate over `collections.posts`
    limit: 10,     // 0 means no limit
  },
  metadata: {
    language: "en",
    title: "Blog Title",
    subtitle: "This is a longer description about your blog.",
    base: "https://example.com/",
    author: {
      name: "Your Name",
      email: "", // Optional
    }
  }
});

  return {
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
    templateFormats: ["md", "njk", "html", "js"]
  };
  
}