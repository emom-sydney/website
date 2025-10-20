// @ts-check
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, ScanCommand } from "@aws-sdk/lib-dynamodb";

import siteConfig from './siteConfig.js';

const client = new DynamoDBClient({
  region: process.env.AWS_REGION || siteConfig.aws.region
});

const docClient = DynamoDBDocumentClient.from(client);

export default async function() {
  const params = {
    TableName: siteConfig.aws.dynamodb.tables.submissions,
    FilterExpression: "formtype = :type",
    ExpressionAttributeValues: {
      ":type": "preregistration"
    }
  };

  try {
    const result = await docClient.send(new ScanCommand(params));
    return {
      count: result.Items?.length || 0,
      maxSubmissions: siteConfig.forms.maxSubmissions
    };
  } catch (error) {
    console.error("Error scanning DynamoDB:", error);
    if (error instanceof Error) {
      console.error(error.message);
    }
    return {
      count: 0,
      maxSubmissions: siteConfig.forms.maxSubmissions,
      error: error instanceof Error ? error.message : 'Unknown error'
    };
  }
}