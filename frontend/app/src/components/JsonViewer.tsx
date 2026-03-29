type JsonViewerProps = {
  data: unknown;
};

export function JsonViewer({ data }: JsonViewerProps) {
  return <pre className="json-viewer">{JSON.stringify(data, null, 2)}</pre>;
}
