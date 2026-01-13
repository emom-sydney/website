import { parse } from "csv-parse/sync";
import fs from "fs";

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

  // add a getYear filter to extract year from date string or Date object
  eleventyConfig.addNunjucksFilter("getYear", (input) => {
    // Normalize input to a Date (or null)
    let d = null;

    // Treat 'now' or empty/undefined/null as current date
    if (input === 'now' || input === undefined || input === null || input === '') {
      d = new Date();
    } else if (input instanceof Date) {
      d = input;
    } else if (typeof input === 'string') {
      const parsed = new Date(input);
      if (!Number.isNaN(parsed.getTime())) {
        d = parsed;
      }
    }

    // If we have a valid Date, return the year
    if (d) {
      return String(d.getFullYear());
    }

    // Fallback: try to pull a 4-digit year out of the string
    const match = String(input).match(/\b(\d{4})\b/);
    return match ? match[1] : "";
  });

  // add a parseDate filter to convert date strings like "Fri, 9 Jan 2026" to Date objects
  eleventyConfig.addNunjucksFilter("parseDate", (dateStr) => {
    if (!dateStr) return null;
    if (dateStr instanceof Date) return dateStr;
    
    // Try to parse the string (works with formats like "Fri, 9 Jan 2026")
    const parsed = new Date(dateStr);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
    return null;
  });

  // Make 'now' available globally for templates
  eleventyConfig.addGlobalData("now", new Date());

  // Helper to check if an artist performed in a specific year
  eleventyConfig.addGlobalData("helpers", {
    artistHasPerformanceInYear: (artist, year, events, performances) => {
      for (const event of events) {
        if (event.Date && event.Date.includes(year)) {
          for (const perf of performances) {
            if (perf.EventID === event.ID && perf.ArtistID === artist.ID) {
              return true;
            }
          }
        }
      }
      return false;
    },
    artistHasPastPerformance: (artist, events, performances, todayTime) => {
      for (const event of events) {
        const eventDate = new Date(event.Date);
        if (!isNaN(eventDate.getTime()) && eventDate.getTime() <= todayTime) {
          for (const perf of performances) {
            if (perf.EventID === event.ID && perf.ArtistID === artist.ID) {
              return true;
            }
          }
        }
      }
      return false;
    }
  });
}