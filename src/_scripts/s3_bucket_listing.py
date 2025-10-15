import boto3
import sys
import argparse
import os

def get_object_emoji(extension):
    # Define a mapping of file extensions to descriptive types
    type_mapping = {
        'mp4': '&#x1F3A5;',  # Movie camera emoji
        'mov': '&#x1F3A5;',  # Movie camera emoji
        'mkv': '&#x1F3A5;',  # Movie camera emoji
        'mp3': '&#x1F508;',  # Loudspeaker emoji
        'wav': '&#x1F508;',  # Loudspeaker emoji
        'flac': '&#x1F508;',  # Loudspeaker emoji
        'jpg': '&#x1F5BC;',  # Picture emoji
        'jpeg': '&#x1F5BC;',  # Picture emoji
        'png': '&#x1F5BC;',  # Picture emoji
        'gif': '&#x1F5BC;',  # Picture emoji
        'pdf': '&#x1F4DA;',  # Book emoji
        'doc': '&#x1F4DA;',  # Book emoji
        'txt': '&#x1F4DA;',  # Book emoji
    }
    return type_mapping.get(extension.lower(), 'unknown')

def main(bucket_name, prefix, output_file, page_title, page_heading):
    # Initialize a session using Amazon S3
    s3 = boto3.client('s3')

    try:
        # List objects in the specified S3 bucket with the given prefix
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    except s3.exceptions.NoSuchBucket:
        print("No HTML was generated because of a problem with the user-supplied bucket or prefix.", file=sys.stderr)
        return
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print("No HTML was generated because of a problem with the user-supplied bucket or prefix.", file=sys.stderr)
        else:
            print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return

    # Generate HTML content
    html_content = f'<html><head><title>{page_title}</title><link rel="stylesheet" type="text/css" href="https://sydney.emom.me/style.css"></head><body>'
    html_content += f'<div class="galleryList"><ul><h3>{page_heading}</h3>'

    # Iterate over the objects and create links with sizes and types
    for obj in response.get('Contents', []):
        object_url = f"https://{bucket_name}.s3.amazonaws.com/{obj['Key']}"
        object_name = obj['Key'].split('/')[-1]  # Extract the object name from the key
        object_size = obj['Size']
        object_extension = os.path.splitext(object_name)[1][1:]  # Get the file extension without the dot
        object_emoji = get_object_emoji(object_extension)  # Map the extension to a descriptive type

        if object_emoji == 'unknown': # skip printing objects that aren't in our type_mappings
           continue

        # Convert size to MB or GB
        if object_size < 1_073_741_824:  # Less than 1 GB
            size_str = f"{object_size / 1048576:.2f} MB"
        else:  # 1 GB or more
            size_str = f"{object_size / 1073741824:.2f} GB"
        
        html_content += f'<li>{object_emoji} <a href="{object_url}">{object_name}</a> ({size_str})</li>'

    html_content += '</ul></div></body></html>'

    # Write the HTML content to a file or print to stdout
    if output_file:
        with open(output_file, 'w') as file:
            file.write(html_content)
        print("HTML file generated successfully.")
    else:
        print(html_content)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate an HTML file listing objects in an S3 bucket.')
    parser.add_argument('-b', '--bucket', required=True, help='The name of the S3 bucket.')
    parser.add_argument('-p', '--prefix', required=True, help='The prefix to filter objects in the S3 bucket.')
    parser.add_argument('-f', '--file', help='The output HTML file name.')
    parser.add_argument('-g', '--page_heading', default='S3 Bucket Listing', help='The heading for the HTML page.')
    parser.add_argument('-t', '--page_title', default='S3 Bucket List', help='The title for the HTML file.')

    args = parser.parse_args()

    main(args.bucket, args.prefix, args.file, args.page_title, args.page_heading)
