import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 정적 export: FastAPI(StaticFiles)가 서빙할 out/ 디렉터리를 생성한다.
  // Hugging Face Spaces 단일 Docker 배포에서 프론트+API를 같은 출처로 묶기 위함.
  output: "export",
  images: { unoptimized: true },
  // 빌드 산출물을 정적 호스팅에 안전하게 매핑(각 경로를 디렉터리/index.html로).
  trailingSlash: true,
};

export default nextConfig;
