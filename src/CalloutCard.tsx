import Card from "react-bootstrap/Card";

type Props = {
  header: string;
  body: string;
};

export default function CalloutCard({ header, body }: Props) {
  return (
    <Card bg="warning">
      <Card.Body>
        <Card.Subtitle>{header}</Card.Subtitle>
        <Card.Text>{body}</Card.Text>
      </Card.Body>
    </Card>
  );
}
