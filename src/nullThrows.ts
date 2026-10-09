export default function nullThrows<T>(t: T | null | undefined): T {
  if (t == null) {
    throw Error("Expected input to be nonnull");
  }
  return t;
}
