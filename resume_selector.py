"""Resume selector — picks the best resume type based on JD keywords."""

from pathlib import Path

RESUME_KEYWORDS = {
    "ai": [
        # LLMs & generative AI
        "llm", "large language model", "generative ai", "gen ai", "genai", "agentic", "agent",
        "rag", "retrieval augmented", "fine-tuning", "fine tuned", "finetuning", "rlhf",
        "prompt engineering", "prompt tuning", "chain of thought", "few-shot", "zero-shot",
        "in-context learning",
        # Providers & frameworks
        "openai", "anthropic", "claude", "gemini", "gpt-4", "gpt-3", "chatgpt", "copilot",
        "langchain", "langgraph", "llamaindex", "llama index", "crewai", "autogen",
        "semantic kernel", "hugging face", "huggingface", "transformers",
        # ML core
        "machine learning", "deep learning", "neural network", "pytorch", "tensorflow",
        "keras", "jax", "scikit-learn", "sklearn", "xgboost", "lightgbm", "catboost",
        "random forest", "gradient boosting", "regression", "classification", "clustering",
        # NLP
        "nlp", "natural language", "text mining", "sentiment analysis", "named entity",
        "tokenization", "bert", "gpt", "word2vec", "spacy", "nltk", "text generation",
        "speech recognition", "text to speech", "conversational ai", "chatbot",
        # Computer vision
        "computer vision", "image recognition", "object detection", "image segmentation",
        "yolo", "opencv", "cnn", "convolutional", "stable diffusion", "diffusion model",
        "image generation", "gan", "generative adversarial",
        # Data science & infra
        "vector database", "pinecone", "weaviate", "chroma", "qdrant", "faiss", "milvus",
        "embeddings", "embedding", "cosine similarity", "semantic search",
        "mlops", "model deployment", "model serving", "inference", "model training",
        "feature engineering", "feature store", "experiment tracking", "mlflow", "wandb",
        "kubeflow", "sagemaker", "vertex ai", "bedrock", "ai platform",
        "transformer", "attention mechanism", "foundation model", "multimodal",
        "ai powered", "ai native", "ai/ml", "ai engineer", "ml engineer",
        "data science", "data scientist", "recommendation system", "anomaly detection",
        "time series", "forecasting", "reinforcement learning", "bayesian",
        "a/b testing", "statistical modeling", "pandas", "numpy", "scipy", "matplotlib",
        "jupyter", "notebook", "databricks", "spark", "pyspark", "hadoop",
    ],
    "frontend": [
        # Core web
        "react", "react.js", "reactjs", "preact", "vue", "vue.js", "vuejs", "angular",
        "svelte", "sveltekit", "solid.js", "solidjs", "lit", "web components",
        "next.js", "nextjs", "nuxt", "nuxt.js", "remix", "gatsby", "astro",
        # Languages
        "typescript", "javascript", "es6", "ecmascript", "jsx", "tsx",
        # Styling
        "tailwind", "tailwindcss", "css", "sass", "scss", "less", "styled-components",
        "css-in-js", "emotion", "css modules", "postcss", "bootstrap", "material ui",
        "mui", "chakra ui", "radix", "shadcn", "ant design", "design system",
        # Build & tooling
        "webpack", "vite", "esbuild", "rollup", "parcel", "turbopack", "babel",
        "swc", "prettier", "eslint", "biome",
        # State & data
        "redux", "zustand", "mobx", "recoil", "jotai", "tanstack", "react query",
        "swr", "apollo client", "urql", "relay",
        "state management", "context api", "hooks",
        # Testing
        "jest", "vitest", "cypress", "playwright", "testing library", "enzyme",
        "storybook", "chromatic", "visual regression",
        # UI/UX
        "html", "html5", "dom", "virtual dom", "ui components", "component library",
        "responsive design", "mobile first", "progressive web", "pwa",
        "accessibility", "wcag", "aria", "a11y", "i18n", "internationalization",
        "frontend performance", "core web vitals", "lighthouse", "lazy loading",
        "code splitting", "server side rendering", "ssr", "static site generation", "ssg",
        "spa", "single page application", "client side rendering",
        "animation", "framer motion", "gsap", "lottie", "three.js", "webgl", "canvas",
        "figma", "sketch", "adobe xd", "zeplin", "pixel perfect",
        # Mobile
        "react native", "expo", "flutter", "ionic", "capacitor",
    ],
    "backend": [
        # Languages
        "java", "python", "golang", "go lang", "rust", "c#", "c++", "ruby", "scala",
        "kotlin", "elixir", "erlang", "clojure", "haskell", "php", "perl", "swift",
        # Frameworks
        "spring boot", "spring", "spring cloud", "spring mvc", "quarkus", "micronaut",
        "hibernate", "jpa", "jdbc", "mybatis",
        "node.js", "nodejs", "express", "express.js", "nestjs", "koa", "hapi", "fastify",
        "fastapi", "django", "flask", "celery", "gunicorn", "uvicorn",
        "rails", "ruby on rails", "sinatra",
        "asp.net", ".net", "dotnet", "entity framework",
        "gin", "echo", "fiber", "actix", "axum", "rocket", "warp",
        # APIs
        "rest api", "restful", "graphql", "grpc", "protobuf", "protocol buffers",
        "websocket", "api design", "api gateway", "swagger", "openapi",
        "oauth", "jwt", "authentication", "authorization", "rbac", "saml", "oidc",
        # Databases
        "postgresql", "postgres", "mysql", "mariadb", "oracle", "sql server", "mssql",
        "sqlite", "cockroachdb", "tidb", "vitess",
        "mongodb", "dynamodb", "cassandra", "couchbase", "firestore", "fauna",
        "redis", "memcached", "valkey", "elasticache",
        "elasticsearch", "opensearch", "solr", "algolia", "meilisearch",
        "neo4j", "graph database", "dgraph", "arangodb",
        "sql", "nosql", "database design", "schema design", "data modeling",
        "migration", "indexing", "query optimization", "orm",
        # Messaging & streaming
        "kafka", "rabbitmq", "sqs", "sns", "kinesis", "pulsar", "nats", "zeromq",
        "event driven", "event sourcing", "cqrs", "pub/sub", "pubsub",
        "message queue", "message broker", "stream processing", "flink", "storm",
        # Architecture
        "microservices", "monolith", "service mesh", "istio", "envoy",
        "distributed systems", "distributed computing", "consensus", "raft", "paxos",
        "load balancing", "rate limiting", "circuit breaker", "saga pattern",
        "domain driven design", "ddd", "clean architecture", "hexagonal",
        "caching", "cdn", "reverse proxy", "api versioning",
        "concurrency", "multithreading", "async", "parallelism",
        "apache camel", "etl", "data pipeline", "airflow", "dagster", "prefect",
        "batch processing", "real-time", "low latency", "high throughput",
    ],
    "sre": [
        # Containers & orchestration
        "kubernetes", "k8s", "docker", "containerd", "podman", "ecs", "eks", "aks", "gke",
        "helm", "kustomize", "operator", "service mesh", "istio", "linkerd",
        "container orchestration", "container runtime",
        # IaC & config management
        "terraform", "terragrunt", "pulumi", "cloudformation", "cdk", "bicep",
        "ansible", "puppet", "chef", "salt", "saltstack",
        "infrastructure as code", "iac", "gitops", "argocd", "flux",
        "packer", "vagrant",
        # CI/CD
        "jenkins", "github actions", "gitlab ci", "circleci", "travis ci", "buildkite",
        "tekton", "spinnaker", "harness", "drone", "argo workflows",
        "ci/cd", "continuous integration", "continuous delivery", "continuous deployment",
        "blue-green", "canary deployment", "rolling update", "feature flag",
        # Observability
        "prometheus", "grafana", "datadog", "splunk", "new relic", "dynatrace",
        "cloudwatch", "stackdriver", "elastic apm", "jaeger", "zipkin", "tempo",
        "opentelemetry", "otel", "fluentd", "fluentbit", "logstash", "loki",
        "observability", "monitoring", "alerting", "logging", "tracing", "metrics",
        "dashboards", "runbook", "postmortem", "root cause analysis", "rca",
        "sla", "slo", "sli", "error budget", "uptime", "availability",
        "incident", "incident management", "incident response", "on-call", "pagerduty",
        "opsgenie", "victorops",
        # Cloud platforms
        "aws", "amazon web services", "ec2", "s3", "lambda", "rds", "vpc", "iam",
        "route53", "cloudfront", "api gateway", "step functions", "fargate", "ecr",
        "gcp", "google cloud", "compute engine", "cloud run", "cloud functions",
        "bigquery", "cloud storage", "pub/sub",
        "azure", "azure devops", "azure functions", "blob storage", "cosmos db",
        "cloud infrastructure", "multi-cloud", "hybrid cloud",
        # OS & networking
        "linux", "unix", "centos", "rhel", "ubuntu", "debian", "amazon linux",
        "bash", "shell scripting", "systemd", "cron",
        "networking", "tcp/ip", "dns", "load balancer", "nginx", "haproxy", "traefik",
        "vpn", "firewall", "security group", "waf", "ssl", "tls", "certificates",
        "cdn", "cloudflare", "akamai", "fastly",
        # HPC & GPU
        "slurm", "hpc", "gpu", "cuda", "nccl", "infiniband",
        # Security
        "devsecops", "vault", "secrets management", "sops",
        "compliance", "soc2", "hipaa", "pci", "gdpr", "fedramp",
        "penetration testing", "vulnerability scanning", "trivy", "snyk",
        "site reliability", "platform engineering", "devops", "infrastructure engineer",
    ],
    "fullstack": [
        # General titles
        "full stack", "fullstack", "full-stack", "end to end", "frontend and backend",
        "software engineer", "software developer", "sde", "new grad", "junior engineer",
        "associate engineer", "mid-level engineer", "senior engineer",
        "product engineer", "application engineer", "platform engineer",
        "web developer", "web engineer", "web application",
        # Stacks & combos
        "mern", "mean", "lamp", "jamstack", "t3 stack",
        "react", "node", "next.js", "express",
        "postgresql", "supabase", "mongodb", "firebase", "prisma", "drizzle",
        "vercel", "netlify", "heroku", "railway", "render", "fly.io",
        # General
        "saas", "b2b", "b2c", "startup", "agile", "scrum", "kanban",
        "cross-functional", "product development", "feature development",
        "technical design", "system design", "code review", "pair programming",
        "test driven", "tdd", "bdd", "unit testing", "integration testing",
        "git", "github", "gitlab", "bitbucket", "version control",
    ],
}

DEFAULT_TYPE = "fullstack"

RESUMES_DIR = Path("resumes")


def get_resume_type(job_title, job_description=""):
    search_text = f"{job_title} {job_description}".lower()
    scores = {}
    matched_keywords = {}

    for resume_type, keywords in RESUME_KEYWORDS.items():
        matches = [kw for kw in keywords if kw in search_text]
        if matches:
            scores[resume_type] = len(matches)
            matched_keywords[resume_type] = matches

    if not scores:
        return DEFAULT_TYPE, {}, {}

    winner = max(scores, key=scores.get)
    return winner, scores, matched_keywords


def get_resume_text(resume_type):
    txt_path = RESUMES_DIR / f"{resume_type}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")
    fallback = RESUMES_DIR / f"{DEFAULT_TYPE}.txt"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    single = Path("resume.txt")
    if single.exists():
        return single.read_text(encoding="utf-8")
    return ""
