import { useState } from "react";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import FormControl from "react-bootstrap/FormControl";

type Props = {
  textarea?: boolean;
  placeholder: string;
  initial: string | null | undefined;
  onSave: (value: string) => unknown;
};

export default function SectionTextFieldRow({
  textarea,
  placeholder,
  initial,
  onSave,
}: Props) {
  const [value, setValue] = useState(initial ?? "");
  return (
    <>
      <Card.Text>
        <FormControl
          as={textarea ? "textarea" : undefined}
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </Card.Text>
      {(value ?? "") !== (initial ?? "") && (
        <Card.Text>
          <Button size="sm" onClick={() => onSave(value)}>
            Save
          </Button>
        </Card.Text>
      )}
    </>
  );
}
