import Badge from "react-bootstrap/Badge";

type Props = {
  tags: Array<string>;
};

const colorLookup: { [tag: string]: string } = {
  Regular: "secondary",
  Scholars: "success",
  "2x Speed": "danger",
  Zoom: "info",
  Transfer: "primary",
};

export default function Tags({ tags }: Props) {
  return (
    <>
      {tags.map((tag) => (
        <Badge className="float-end" pill bg={colorLookup[tag] ?? "dark"} key={tag}>
          {tag}
        </Badge>
      ))}
    </>
  );
}
