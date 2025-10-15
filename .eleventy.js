export default function (eleventyConfig) {
  eleventyConfig.setInputDirectory("src");
  // eleventyConfig.setInputDirectory("scripts");
  eleventyConfig.addPassthroughCopy("assets/img");
  eleventyConfig.addPassthroughCopy("assets/css");
  // eleventyConfig.addPassthroughCopy("scripts");
  eleventyConfig.setIncludesDirectory("_includes");
  eleventyConfig.setOutputDirectory("_site");
  }
