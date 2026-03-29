type CopyButtonProps = {
  value: string;
};

export function CopyButton({ value }: CopyButtonProps) {
  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
  };

  return (
    <button type="button" className="copy-button" onClick={handleCopy}>
      Copy
    </button>
  );
}
