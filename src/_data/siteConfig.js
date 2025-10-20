// @ts-check

const env = process.env.ELEVENTY_ENV || 'development';

const configs = {
  development: {
    aws: {
      region: "ap-southeast-2",
      dynamodb: {
        tables: {
          submissions: "ContactFormEntriesDev",
        },
        indexes: {
          submissionsByType: "formtype-timestamp-index"
        }
      },
      s3: {
        buckets: {
          gallery: "emomsydney-web"
        }
      }
    },
    forms: {
      maxSubmissions: 7
    }
  },
  production: {
    aws: {
      region: "ap-southeast-2",
      dynamodb: {
        tables: {
          submissions: "ContactFormEntries",
        },
        indexes: {
          submissionsByType: "formtype-timestamp-index"
        }
      },
      s3: {
        buckets: {
          gallery: "sydney.emom.me"
        }
      }
    },
    forms: {
      maxSubmissions: 7
    }
  }
};

export default configs[env];