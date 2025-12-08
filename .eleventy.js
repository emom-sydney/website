export default function (eleventyConfig) {
  eleventyConfig.setInputDirectory("src");
   eleventyConfig.addPassthroughCopy("assets");
  eleventyConfig.setIncludesDirectory("_includes");
  eleventyConfig.setOutputDirectory("_site");
  }
