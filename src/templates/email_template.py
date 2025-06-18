from datetime import datetime
from typing import List, Dict, Any


def generate_email_template(posts_data: List[Dict[str, Any]], subreddit_list: List[str]) -> str:

    html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Reddit Daily Digest</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                    line-height: 1.5;
                    color: #1a1a1b;
                    background-color: #f6f7f8;
                }
                
                .container {
                    max-width: 650px;
                    margin: 0 auto;
                    background-color: #ffffff;
                }
                
                .header {
                    background: linear-gradient(135deg, #FF4500 0%, #FF6B35 100%);
                    color: white;
                    padding: 25px 20px;
                    text-align: center;
                }
                
                .header h1 {
                    font-size: 26px;
                    margin-bottom: 8px;
                }
                
                .summary-box {
                    background-color: #f0f8ff;
                    border-left: 4px solid #0079D3;
                    padding: 15px;
                    margin: 20px;
                    border-radius: 4px;
                }
                
                .summary-box h3 {
                    color: #0079D3;
                    margin-bottom: 10px;
                }
                
                .subreddit-section {
                    margin: 15px 20px;
                    border: 1px solid #edeff1;
                    border-radius: 8px;
                    overflow: hidden;
                }
                
                .subreddit-header {
                    background-color: #f6f7f8;
                    padding: 12px 15px;
                    cursor: pointer;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .subreddit-name {
                    font-weight: 600;
                    color: #0079D3;
                    font-size: 16px;
                }
                
                .post-count {
                    background-color: #0079D3;
                    color: white;
                    padding: 2px 8px;
                    border-radius: 12px;
                    font-size: 12px;
                }
                
                .posts-list {
                    padding: 0;
                }
                
                .post-item {
                    border-bottom: 1px solid #edeff1;
                    padding: 12px 15px;
                    transition: background-color 0.2s;
                }
                
                .post-item:last-child {
                    border-bottom: none;
                }
                
                .post-item:hover {
                    background-color: #f6f7f8;
                }
                
                .post-title {
                    font-weight: 500;
                    margin-bottom: 6px;
                    font-size: 15px;
                }
                
                .post-title a {
                    color: #1a1a1b;
                    text-decoration: none;
                }
                
                .post-title a:hover {
                    color: #0079D3;
                    text-decoration: underline;
                }
                
                .post-summary {
                    color: #7c7c7c;
                    font-size: 13px;
                    line-height: 1.4;
                }
                
                .top-posts {
                    background-color: #fff5f5;
                    margin: 20px;
                    padding: 15px;
                    border-radius: 8px;
                    border: 1px solid #ffdddd;
                }
                
                .top-posts h3 {
                    color: #d93a00;
                    margin-bottom: 10px;
                    font-size: 16px;
                }
                
                .footer {
                    background-color: #1a1a1b;
                    color: #ffffff;
                    padding: 20px;
                    text-align: center;
                    font-size: 13px;
                }
                
                .footer a {
                    color: #0079D3;
                    text-decoration: none;
                }
                
                .view-more {
                    text-align: center;
                    padding: 15px;
                    background-color: #f6f7f8;
                    border-top: 1px solid #edeff1;
                }
                
                .view-more a {
                    color: #0079D3;
                    text-decoration: none;
                    font-weight: 500;
                }
                
                @media only screen and (max-width: 600px) {
                    .header h1 {
                        font-size: 22px;
                    }
                    .post-title {
                        font-size: 14px;
                    }
                    .post-summary {
                        font-size: 12px;
                    }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Reddit Daily Digest</h1>
                    <div style="font-size: 14px; opacity: 0.9;">""" + datetime.now().strftime('%A, %B %d, %Y') + """</div>
                </div>
                
                <div class="summary-box">
                    <h3>📈 Today's Overview</h3>
                    <p>""" + f"{len(posts_data)} posts from {len(subreddit_list)} subreddits: " + ', '.join([f'r/{sub}' for sub in subreddit_list]) + """</p>
                </div>
        """

    return html
