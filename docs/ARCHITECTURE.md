# RoadMate AI Architecture

## Runtime plane
The browser/mobile client provides text, microphone input, location and optional camera frames. FastAPI exposes REST and WebSocket interfaces. The orchestrator interprets intent and calls isolated tools for Places, Routes, Spotify, RAG and ML ranking.

## Voice plane
The included web client provides browser speech recognition and speech synthesis so the project works locally. The production path replaces the local speech loop with Gemini Live for persistent bidirectional audio/video/text sessions while preserving the same tool interfaces.

## Location intelligence
Places search finds candidate POIs. The recommendation layer ranks results. Routes computes directions and traffic-aware ETA when the Google Maps key is configured. The assistant can recommend route changes but should never treat a machine-vision traffic-light observation as authority to proceed.

## Knowledge/RAG plane
PDF/text documents are chunked and indexed locally with TF-IDF for a dependency-light demo. Production can replace this with Vertex AI embeddings plus a managed vector store while retaining source metadata for grounded answers.

## ML plane
`ml/train_place_ranker.py` demonstrates supervised ranking from interaction features. The same event stream can later train ETA models, intent models and computer-vision models in Vertex AI.

## Data plane
Every interaction can emit structured events locally and later to Pub/Sub. BigQuery stores analytics/model features. This supports quality monitoring, recommendation acceptance, agent latency, tool success rates and model evaluation.
